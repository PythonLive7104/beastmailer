"""Public tracking endpoints: open pixel, click redirect, unsubscribe.

These are the only unauthenticated views in the app — they are reached from inside
a delivered email, so they carry an unguessable per-recipient token instead of a
session. Each one fails quietly: a tracking problem must never show the recipient
an error page or, worse, block their click.
"""
import base64

from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import CampaignRecipient, Contact

# A 1x1 transparent GIF, served under a .png name because some clients refuse to
# load an <img> whose extension looks like tracking. Bytes inline so the pixel
# needs no file on disk.
_PIXEL = base64.b64decode(
    b"R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


def _pixel_response() -> HttpResponse:
    resp = HttpResponse(_PIXEL, content_type="image/gif")
    # Caching would hide every open after the first, including across recipients
    # behind the same corporate proxy.
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    resp["Pragma"] = "no-cache"
    return resp


@xframe_options_exempt
def track_open(request, token):
    """Record an open, then return the pixel whatever happens."""
    recipient = CampaignRecipient.objects.filter(token=token).select_related("campaign").first()
    if recipient is not None:
        now = timezone.now()
        updates = {"open_count": recipient.open_count + 1}
        if recipient.opened_at is None:
            updates["opened_at"] = now
        # Only promote the status forward: a click already outranks an open.
        if recipient.status == CampaignRecipient.Status.SENT:
            updates["status"] = CampaignRecipient.Status.OPENED
        CampaignRecipient.objects.filter(pk=recipient.pk).update(**updates)
    return _pixel_response()


def track_click(request, token):
    """Count the click, then forward to the original URL.

    Only http(s) targets are followed: without that check the redirect would happily
    emit `javascript:` or `data:` URLs supplied by whoever composed the campaign.
    """
    target = request.GET.get("u") or ""
    if not target.lower().startswith(("http://", "https://")):
        return HttpResponse("Invalid link.", status=400)

    recipient = CampaignRecipient.objects.filter(token=token).first()
    if recipient is not None:
        now = timezone.now()
        updates = {
            "click_count": recipient.click_count + 1,
            "status": CampaignRecipient.Status.CLICKED,
        }
        if recipient.clicked_at is None:
            updates["clicked_at"] = now
        # A click proves the mail was opened, even when the pixel was blocked.
        if recipient.opened_at is None:
            updates["opened_at"] = now
            updates["open_count"] = recipient.open_count + 1
        CampaignRecipient.objects.filter(pk=recipient.pk).update(**updates)
    return HttpResponseRedirect(target)


_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#0e1116;color:#e6e9ef;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px}}
 .card{{max-width:460px;text-align:center;background:#161b22;border:1px solid #263041;
       border-radius:14px;padding:32px}}
 h1{{font-size:19px;margin:0 0 10px}} p{{color:#97a3b6;line-height:1.6;margin:0}}
 form{{margin-top:18px}}
 button{{background:#6d5efc;color:#fff;border:0;border-radius:8px;padding:10px 18px;
         font-size:14px;cursor:pointer}}
</style></head><body><div class="card"><h1>{title}</h1><p>{message}</p>{extra}</div></body></html>
"""


def _page(title: str, message: str, extra: str = "", status: int = 200) -> HttpResponse:
    return HttpResponse(_PAGE.format(title=title, message=message, extra=extra), status=status)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    """One-click unsubscribe (RFC 8058).

    Gmail and Yahoo POST here directly from their own UI, so POST must opt the
    contact out with no confirmation step; GET shows a page with a button for people
    who click the link in the footer.
    """
    contact = Contact.objects.filter(unsubscribe_token=token).first()
    if contact is None:
        return _page("Link not recognised",
                     "This unsubscribe link is no longer valid. "
                     "Reply to the email and we will remove you by hand.", status=404)

    already = contact.status == Contact.Status.UNSUBSCRIBED
    if request.method == "POST" or request.GET.get("confirm") == "1":
        if not already:
            Contact.objects.filter(pk=contact.pk).update(
                status=Contact.Status.UNSUBSCRIBED,
                status_reason="Unsubscribed via email link",
                unsubscribed_at=timezone.now(),
            )
            # Stop the in-flight campaigns too, not just future ones.
            CampaignRecipient.objects.filter(
                contact=contact, status=CampaignRecipient.Status.PENDING
            ).update(status=CampaignRecipient.Status.SKIPPED, error="Contact unsubscribed")
            CampaignRecipient.objects.filter(
                contact=contact, unsubscribed_at__isnull=True, sent_at__isnull=False
            ).update(unsubscribed_at=timezone.now())
        return _page("You're unsubscribed",
                     f"{contact.email} will not receive any further emails from us.")

    if already:
        return _page("Already unsubscribed",
                     f"{contact.email} is not on our mailing list.")

    return _page(
        "Unsubscribe?",
        f"Confirm that {contact.email} should stop receiving these emails.",
        extra='<form method="post"><button type="submit">Unsubscribe me</button></form>',
    )
