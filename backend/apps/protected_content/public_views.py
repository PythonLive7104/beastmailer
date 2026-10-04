"""Public, unauthenticated endpoints that serve protected documents.

These live outside /api/ (like the /r/ and /t/ tracking routes) because they are
opened directly from a link in an email. There is no session; authorization is
the gate in gate.py plus the per-document passcode.
"""
import mimetypes
import os
import re

from django.db.models import F
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt

from .export import _deterrent_js
from .gate import check_access, check_asset_access
from .htmlmin import minify_html
from .models import ProtectedAccessLog, ProtectedAsset, ProtectedDocument

# Friendly messages per denial outcome.
_DENIAL_MESSAGES = {
    ProtectedAccessLog.OUTCOME_INACTIVE: ("Unavailable", "This content is no longer available."),
    ProtectedAccessLog.OUTCOME_EXPIRED: ("Expired", "This content has expired and can no longer be viewed."),
    ProtectedAccessLog.OUTCOME_OVER_LIMIT: ("View limit reached", "This content has reached its maximum number of views."),
    ProtectedAccessLog.OUTCOME_DENIED_REFERRER: ("Access denied", "This content can only be opened from an authorized site."),
}

_SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
body{{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:#0f1115;color:#e6e8eb;display:flex;min-height:100vh;align-items:center;justify-content:center}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:32px;max-width:380px;width:90%}}
h1{{font-size:18px;margin:0 0 12px}} p{{color:#9aa4b2;margin:0 0 20px}}
input{{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:8px;border:1px solid #30374a;
background:#0f1115;color:#e6e8eb;font-size:15px}}
button{{margin-top:14px;width:100%;padding:11px;border:0;border-radius:8px;background:#4f7cff;color:#fff;
font-size:15px;font-weight:600;cursor:pointer}} .err{{color:#ff8080;margin:10px 0 0;font-size:13px}}
</style></head><body><div class="card">{body}</div></body></html>"""


def _page(title: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(_SHELL.format(title=escape(title), body=body), status=status)


def _passcode_form(doc, error: str = "") -> HttpResponse:
    err = f'<p class="err">{escape(error)}</p>' if error else ""
    body = (
        f"<h1>Protected content</h1>"
        f"<p>Enter the passcode to view &ldquo;{escape(doc.name)}&rdquo;.</p>"
        f'<form method="post"><input type="password" name="passcode" autofocus '
        f'placeholder="Passcode" autocomplete="off">{err}'
        f'<button type="submit">Unlock</button></form>'
    )
    return _page("Protected content", body, status=401)


def _deterrent_script(doc) -> str:
    js = _deterrent_js(doc)
    return f"<script>{js}</script>" if js else ""


def _download_filename(doc) -> str:
    """A safe download filename that keeps the real extension.

    Prefers the original uploaded filename; otherwise uses the display name and
    appends an extension guessed from the content type, so the file stays usable.
    """
    name = doc.original_filename or doc.name or "download"
    name = os.path.basename(name).replace('"', "")
    if not os.path.splitext(name)[1]:
        ext = mimetypes.guess_extension(doc.content_type.split(";")[0].strip()) if doc.content_type else None
        if ext:
            name += ext
    # Strip anything odd from the header value.
    return re.sub(r"[\r\n]", "", name)


def _serve_payload(doc) -> HttpResponse:
    # Count the view atomically, then hand over the decrypted payload.
    ProtectedDocument.objects.filter(pk=doc.pk).update(view_count=F("view_count") + 1)
    payload = doc.get_payload()
    if doc.kind == ProtectedDocument.KIND_FILE:
        resp = HttpResponse(payload, content_type=doc.content_type or "application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{_download_filename(doc)}"'
        return resp
    html = payload.decode("utf-8", errors="replace")
    if doc.minify:
        html = minify_html(html)
    html += _deterrent_script(doc)
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@csrf_exempt
def view_document(request, slug):
    try:
        doc = get_object_or_404(ProtectedDocument, slug=slug)
    except Http404:
        return _page("Not found", "<h1>Not found</h1><p>No such content.</p>", status=404)

    passcode = request.POST.get("passcode") if request.method == "POST" else None
    granted, outcome = check_access(doc, request, passcode=passcode)

    if granted:
        return _serve_payload(doc)

    if outcome == ProtectedAccessLog.OUTCOME_DENIED_PASSCODE:
        # A wrong attempt (POST) honors the configured action; a first view (GET)
        # always just shows the prompt.
        if request.method == "POST":
            if doc.wrong_passcode_action == ProtectedDocument.WRONG_BLANK:
                return HttpResponse("", content_type="text/html; charset=utf-8", status=401)
            if doc.wrong_passcode_action == ProtectedDocument.WRONG_BACK:
                return HttpResponse(
                    "<!doctype html><script>history.back()</script>",
                    content_type="text/html; charset=utf-8", status=401,
                )
            return _passcode_form(doc, "Incorrect passcode.")
        return _passcode_form(doc, "")

    title, msg = _DENIAL_MESSAGES.get(outcome, ("Access denied", "You can't view this content."))
    return _page(title, f"<h1>{escape(title)}</h1><p>{escape(msg)}</p>", status=403)


@csrf_exempt
def view_asset(request, slug, asset_id):
    """Serve a gated asset (image, etc.) belonging to a protected page."""
    asset = get_object_or_404(ProtectedAsset, pk=asset_id, document__slug=slug)
    doc = asset.document
    granted, _ = check_asset_access(doc, request)
    if not granted:
        return HttpResponse(status=403)
    resp = HttpResponse(asset.get_payload(), content_type=asset.content_type or "application/octet-stream")
    # Assets are per-link and may change; don't let shared caches hold them.
    resp["Cache-Control"] = "private, no-store"
    return resp
