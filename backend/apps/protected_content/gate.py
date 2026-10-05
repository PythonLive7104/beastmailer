"""Server-side access gate for protected documents.

This is where the real enforcement lives: nothing of the payload leaves the
server until a request passes every check, and every attempt is recorded. The
checks run in a fixed order and each failure is logged with its own outcome.
"""
from django.utils import timezone

from .export import parse_domains
from .models import ProtectedAccessLog, ProtectedDocument


def client_ip(request) -> str | None:
    # Behind nginx the real client is in X-Forwarded-For (first hop).
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _referrer_ok(doc: ProtectedDocument, referrer: str) -> bool:
    allowed = [r.strip().lower() for r in (doc.allowed_referrers or "").split(",") if r.strip()]
    if not allowed:
        return True
    ref = (referrer or "").lower()
    return any(a in ref for a in allowed)


def _domain_ok(doc: ProtectedDocument, request) -> bool:
    """Domain lock: the host this link was opened on must be one we licensed.

    Unlike the referrer check (which inspects where the visitor came *from*), this
    pins the host serving the link, so a copy of the deployment under another
    domain stops working. Subdomains of a listed domain pass.
    """
    allowed = parse_domains(doc.allowed_domains)
    if not allowed:
        return True
    host = (request.get_host() or "").split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith("." + d) for d in allowed)


def log(doc: ProtectedDocument, request, outcome: str):
    ProtectedAccessLog.objects.create(
        document=doc,
        ip=client_ip(request),
        referrer=(request.META.get("HTTP_REFERER", "") or "")[:500],
        outcome=outcome,
    )


def check_access(doc: ProtectedDocument, request, passcode: str | None = None):
    """Run the gate. Returns (granted: bool, outcome: str).

    outcome is one of ProtectedAccessLog.OUTCOME_*; the caller decides what to
    render for each. This function logs the attempt itself.
    """
    if not doc.is_active:
        log(doc, request, ProtectedAccessLog.OUTCOME_INACTIVE)
        return False, ProtectedAccessLog.OUTCOME_INACTIVE

    if doc.expires_at and timezone.now() >= doc.expires_at:
        log(doc, request, ProtectedAccessLog.OUTCOME_EXPIRED)
        return False, ProtectedAccessLog.OUTCOME_EXPIRED

    if doc.max_views is not None and doc.view_count >= doc.max_views:
        log(doc, request, ProtectedAccessLog.OUTCOME_OVER_LIMIT)
        return False, ProtectedAccessLog.OUTCOME_OVER_LIMIT

    if not _referrer_ok(doc, request.META.get("HTTP_REFERER", "")):
        log(doc, request, ProtectedAccessLog.OUTCOME_DENIED_REFERRER)
        return False, ProtectedAccessLog.OUTCOME_DENIED_REFERRER

    if not _domain_ok(doc, request):
        log(doc, request, ProtectedAccessLog.OUTCOME_DENIED_DOMAIN)
        return False, ProtectedAccessLog.OUTCOME_DENIED_DOMAIN

    if doc.requires_passcode and not doc.check_passcode(passcode or ""):
        # Only log an explicit denial when a passcode was actually attempted,
        # so merely opening the page (and seeing the prompt) isn't noise.
        if passcode is not None:
            log(doc, request, ProtectedAccessLog.OUTCOME_DENIED_PASSCODE)
        return False, ProtectedAccessLog.OUTCOME_DENIED_PASSCODE

    log(doc, request, ProtectedAccessLog.OUTCOME_GRANTED)
    return True, ProtectedAccessLog.OUTCOME_GRANTED


def check_asset_access(doc: ProtectedDocument, request):
    """Gate for assets embedded in a protected page (images, etc.).

    Assets load inside <img> tags, so a passcode can't be supplied per request
    and view counting doesn't apply. The meaningful checks are active, expiry and
    referrer — enough to stop hotlinking and keep paths unguessable. Only denials
    are logged, so a page with many images doesn't flood the audit trail.
    """
    if not doc.is_active:
        log(doc, request, ProtectedAccessLog.OUTCOME_INACTIVE)
        return False, ProtectedAccessLog.OUTCOME_INACTIVE
    if doc.expires_at and timezone.now() >= doc.expires_at:
        log(doc, request, ProtectedAccessLog.OUTCOME_EXPIRED)
        return False, ProtectedAccessLog.OUTCOME_EXPIRED
    if not _referrer_ok(doc, request.META.get("HTTP_REFERER", "")):
        log(doc, request, ProtectedAccessLog.OUTCOME_DENIED_REFERRER)
        return False, ProtectedAccessLog.OUTCOME_DENIED_REFERRER
    if not _domain_ok(doc, request):
        log(doc, request, ProtectedAccessLog.OUTCOME_DENIED_DOMAIN)
        return False, ProtectedAccessLog.OUTCOME_DENIED_DOMAIN
    return True, ProtectedAccessLog.OUTCOME_GRANTED
