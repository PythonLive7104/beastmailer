"""Delivery for campaign email: route selection, provider drivers, tracking.

Only the standard library is used here, matching the auto-reply engine: SMTP routes
go through `apps.proxies.net` (so campaigns inherit the proxy pool) and the HTTP
providers are driven with `urllib`, so adding SendGrid or Mailgun costs no new
dependency.
"""
from __future__ import annotations

import base64
import json
import re
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage as PyEmailMessage

from django.conf import settings
from django.utils import timezone

from apps.automation.engine import _smtp_connect, build_context, html_to_text, render_template
from apps.proxies.models import Proxy
from apps.proxies.net import ProxySMTP, ProxySMTP_SSL

from .models import Campaign, CampaignRecipient, CampaignSender, Contact

HTTP_TIMEOUT = 30


class SendError(Exception):
    """A send that failed. `permanent` marks a rejection worth no retry."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


# --------------------------------------------------------------------------- #
# Public URLs for tracking
# --------------------------------------------------------------------------- #
# The engine runs outside a request, so it can't build absolute URLs from one.
# PUBLIC_BASE_URL is the app's own origin, e.g. https://generalautoreply.info.


def _public_base() -> str:
    return (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")


def open_pixel_url(recipient: CampaignRecipient) -> str:
    return f"{_public_base()}/t/o/{recipient.token}.png"


def click_url(recipient: CampaignRecipient, target: str) -> str:
    return f"{_public_base()}/t/c/{recipient.token}/?u={urllib.parse.quote(target, safe='')}"


def unsubscribe_url(contact: Contact) -> str:
    return f"{_public_base()}/t/u/{contact.unsubscribe_token}/"


# --------------------------------------------------------------------------- #
# Body preparation
# --------------------------------------------------------------------------- #
_HREF = re.compile(r'href=(["\'])(https?://[^"\']+)\1', re.IGNORECASE)


def rewrite_links(html: str, recipient: CampaignRecipient) -> str:
    """Point every http(s) link at the click tracker, which redirects on to it.

    Already-tracked links and the unsubscribe link are left alone: double-wrapping
    would break the redirect chain and let an unsubscribe count as a content click.
    """
    base = _public_base()

    def repl(m: re.Match) -> str:
        quote, url = m.group(1), m.group(2)
        if base and url.startswith(f"{base}/t/"):
            return m.group(0)
        return f"href={quote}{click_url(recipient, url)}{quote}"

    return _HREF.sub(repl, html)


# Preview text: a hidden block at the very top of the body. Inboxes show the first
# text they find after the subject, so without this they show whatever the markup
# happens to start with — often "View in browser" or nothing. The trailing entities
# stop the client spilling body copy into the preview after the real text ends.
_PREHEADER_TEMPLATE = (
    '<div style="display:none;max-height:0;overflow:hidden;opacity:0;'
    'mso-hide:all;font-size:1px;line-height:1px;color:transparent;">{text}'
    '&#847;&zwnj;&nbsp;' * 1 + '</div>'
)


def _inject_preheader(html: str, preheader: str) -> str:
    """Put the preview text first in the document, inside <body> when there is one."""
    if not preheader:
        return html
    block = _PREHEADER_TEMPLATE.format(text=preheader) + "&#847;&zwnj;&nbsp;" * 20
    lower = html.lower()
    if "<body" in lower:
        close = lower.index(">", lower.index("<body")) + 1
        return html[:close] + block + html[close:]
    return block + html


def build_body(campaign: Campaign, recipient: CampaignRecipient, context: dict) -> tuple[str, bool]:
    """Render one recipient's copy: placeholders, preview text, tracking, open pixel."""
    body = render_template(campaign.body, context, workspace=campaign.workspace)
    is_html = campaign.is_html
    if not is_html:
        return body, False
    if campaign.preheader:
        body = _inject_preheader(
            body, render_template(campaign.preheader, context, workspace=campaign.workspace)
        )
    if campaign.track_clicks:
        body = rewrite_links(body, recipient)
    if campaign.track_opens:
        pixel = (
            f'<img src="{open_pixel_url(recipient)}" width="1" height="1" '
            'alt="" style="display:block;border:0;outline:none;" />'
        )
        # Inside </body> when there is one, so the pixel stays within the document.
        lower = body.lower()
        body = (body[: lower.rindex("</body>")] + pixel + body[lower.rindex("</body>") :]
                if "</body>" in lower else body + pixel)
    return body, True


def recipient_context(campaign: Campaign, recipient: CampaignRecipient, sender: CampaignSender) -> dict:
    """Template variables for a campaign send.

    Starts from the auto-reply engine's own context so every {{tag}} the client
    already knows keeps working, then adds the contact and campaign fields.
    """
    contact = recipient.contact
    mailbox = sender.mailbox if sender.kind == CampaignSender.Kind.MAILBOX else None
    # build_context() wants an incoming message; a campaign has none, so pass an
    # unsaved stand-in addressed from the contact. Tags like {{sender_name}} then
    # resolve to the recipient, which is what a campaign author means by them.
    from apps.mail.models import EmailMessage as MailMessage
    from apps.mailboxes.models import Mailbox

    stand_in = MailMessage(
        subject=campaign.subject,
        from_addr=contact.email,
        from_name=contact.full_name,
        body="",
        received_at=timezone.now(),
    )
    box = mailbox or Mailbox(name=sender.name, email_address=sender.sender_email)
    context = build_context(stand_in, box, template=None)
    context.update({
        "email": contact.email,
        "first_name": contact.first_name or contact.full_name or "there",
        "last_name": contact.last_name,
        "full_name": contact.full_name or contact.email,
        "company": contact.company,
        "campaign_name": campaign.name,
        "unsubscribe_url": unsubscribe_url(contact),
        # A bare link is the common case in a footer; give them ready-made markup too.
        "unsubscribe_link": f'<a href="{unsubscribe_url(contact)}">Unsubscribe</a>',
        "workspace_name": campaign.workspace.name,
    })
    # Imported CSV columns win nothing over built-ins: a column called "email" must
    # not be able to redirect the send.
    for key, value in (contact.fields or {}).items():
        context.setdefault(str(key), "" if value is None else str(value))
    return context


# --------------------------------------------------------------------------- #
# Provider drivers
# --------------------------------------------------------------------------- #


def _headers(sender: CampaignSender, contact: Contact) -> dict:
    """Headers every campaign email carries.

    List-Unsubscribe plus List-Unsubscribe-Post is RFC 8058 one-click unsubscribe,
    which Gmail and Yahoo have required from bulk senders since February 2024.
    """
    head = {
        "List-Unsubscribe": f"<{unsubscribe_url(contact)}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        # Marks the mail as bulk so auto-responders stay quiet (RFC 3834).
        "Precedence": "bulk",
    }
    if sender.reply_to:
        head["Reply-To"] = sender.reply_to
    return head


def _from_header(sender: CampaignSender, from_override: str = "") -> str:
    """The From line. `from_override` lets an auto-reply keep its own mailbox
    identity while borrowing this route's transport."""
    if from_override:
        return from_override
    addr = sender.sender_email
    name = sender.from_name or (sender.mailbox.name if sender.mailbox else "")
    return f"{name} <{addr}>" if name else addr


def _smtp_for(sender: CampaignSender):
    """Open an SMTP connection for a mailbox / relay / SES route."""
    if sender.kind == CampaignSender.Kind.MAILBOX:
        # Reuse the auto-reply connector: it already retries across the proxy pool
        # and refuses to fall back to the bare server IP when proxies are required.
        return _smtp_connect(sender.mailbox)

    host = sender.smtp_host
    if sender.kind == CampaignSender.Kind.SES:
        # SES publishes one SMTP endpoint per region.
        host = host or f"email-smtp.{sender.region or 'us-east-1'}.amazonaws.com"
    port = sender.smtp_port or 587
    proxy = Proxy.pick_random(sender.workspace) if sender.use_proxy else None
    if sender.smtp_use_tls:
        smtp = ProxySMTP(host, port, proxy=proxy, timeout=30)
        smtp.starttls(context=ssl.create_default_context())
    elif port == 465:
        smtp = ProxySMTP_SSL(host, port, proxy=proxy, timeout=30)
    else:
        smtp = ProxySMTP(host, port, proxy=proxy, timeout=30)
    if sender.username:
        smtp.login(sender.username, sender.secret)
    return smtp


def _send_smtp(sender, contact, subject, body, is_html, attachments, from_override="", extra_headers=None):
    py = PyEmailMessage()
    py["From"] = _from_header(sender, from_override)
    py["To"] = contact.email
    py["Subject"] = subject
    for key, value in {**_headers(sender, contact), **(extra_headers or {})}.items():
        py[key] = value
    if is_html:
        py.set_content(html_to_text(body))
        py.add_alternative(body, subtype="html")
    else:
        py.set_content(body)
    for att in attachments:
        try:
            att.file.open("rb")
            data = att.file.read()
            att.file.close()
            maintype, _, subtype = (att.content_type or "application/octet-stream").partition("/")
            py.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                              filename=att.file.name.split("/")[-1])
        except Exception:  # noqa: BLE001 - a missing file must not sink the whole send
            continue

    smtp = _smtp_for(sender)
    try:
        smtp.send_message(py)
    except smtplib.SMTPRecipientsRefused as exc:
        raise SendError(f"Recipient refused: {exc}", permanent=True) from exc
    except smtplib.SMTPResponseException as exc:
        # 5xx is a hard rejection; 4xx is worth another attempt later.
        raise SendError(f"{exc.smtp_code} {exc.smtp_error}", permanent=500 <= exc.smtp_code < 600) from exc
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001
            pass


def _http_post(url: str, data: bytes, headers: dict) -> str:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        # 4xx means the request itself is wrong (bad address, rejected content):
        # retrying sends the identical request, so treat it as permanent.
        raise SendError(f"HTTP {exc.code}: {detail}", permanent=400 <= exc.code < 500) from exc
    except urllib.error.URLError as exc:
        raise SendError(f"Network error: {exc.reason}") from exc


def _send_sendgrid(sender, contact, subject, body, is_html, attachments, from_override="", extra_headers=None):
    payload = {
        "personalizations": [{"to": [{"email": contact.email}]}],
        "from": _sendgrid_from(sender, from_override),
        "subject": subject,
        # Both parts, always: an HTML-only bulk email is a well-known spam signal,
        # and text/plain must come first — receivers take the last part they can render.
        "content": ([{"type": "text/plain", "value": html_to_text(body)},
                     {"type": "text/html", "value": body}]
                    if is_html else [{"type": "text/plain", "value": body}]),
        "headers": {**_headers(sender, contact), **(extra_headers or {})},
    }
    if sender.reply_to:
        payload["reply_to"] = {"email": sender.reply_to}
    _http_post(
        "https://api.sendgrid.com/v3/mail/send",
        json.dumps(payload).encode(),
        {"Authorization": f"Bearer {sender.secret}", "Content-Type": "application/json"},
    )


def _send_mailgun(sender, contact, subject, body, is_html, attachments, from_override="", extra_headers=None):
    domain = sender.domain or sender.sender_email.split("@")[-1]
    fields = {
        "from": _from_header(sender, from_override),
        "to": contact.email,
        "subject": subject,
        **({"html": body, "text": html_to_text(body)} if is_html else {"text": body}),
    }
    if sender.reply_to:
        fields["h:Reply-To"] = sender.reply_to
    for key, value in {**_headers(sender, contact), **(extra_headers or {})}.items():
        fields[f"h:{key}"] = value
    auth = base64.b64encode(f"api:{sender.secret}".encode()).decode()
    _http_post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        urllib.parse.urlencode(fields).encode(),
        {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
    )


def _send_postmark(sender, contact, subject, body, is_html, attachments, from_override="", extra_headers=None):
    payload = {
        "From": _from_header(sender, from_override),
        "To": contact.email,
        "Subject": subject,
        **({"HtmlBody": body, "TextBody": html_to_text(body)} if is_html else {"TextBody": body}),
        # Bulk mail belongs on a broadcast stream; Postmark rejects it on the
        # transactional stream, which is the mistake that gets accounts suspended.
        "MessageStream": "broadcast",
        "Headers": [{"Name": k, "Value": v}
                    for k, v in {**_headers(sender, contact), **(extra_headers or {})}.items()],
    }
    if sender.reply_to:
        payload["ReplyTo"] = sender.reply_to
    _http_post(
        "https://api.postmarkapp.com/email",
        json.dumps(payload).encode(),
        {"X-Postmark-Server-Token": sender.secret, "Content-Type": "application/json",
         "Accept": "application/json"},
    )


_DRIVERS = {
    CampaignSender.Kind.SENDGRID: _send_sendgrid,
    CampaignSender.Kind.MAILGUN: _send_mailgun,
    CampaignSender.Kind.POSTMARK: _send_postmark,
}


def _sendgrid_from(sender: CampaignSender, from_override: str = "") -> dict:
    """SendGrid wants From as a structured object, not a header string."""
    if from_override:
        name, _, rest = from_override.rpartition("<")
        addr = rest.rstrip(">").strip() if rest else from_override
        return {"email": addr, "name": name.strip().strip('"') if name else ""}
    return {"email": sender.sender_email, "name": sender.from_name or ""}


def deliver(sender: CampaignSender, contact: Contact, subject: str, body: str,
            is_html: bool, attachments=(), from_override: str = "",
            extra_headers: dict | None = None) -> None:
    """Hand one message to whichever provider this route represents.

    `from_override` and `extra_headers` exist for the auto-reply fallback, which
    borrows a campaign route's transport but must keep the mailbox's own From
    address and its threading headers.
    """
    driver = _DRIVERS.get(sender.kind)
    if driver:
        driver(sender, contact, subject, body, is_html, attachments, from_override, extra_headers)
    else:
        _send_smtp(sender, contact, subject, body, is_html, attachments, from_override, extra_headers)


def send_test(sender: CampaignSender, to_addr: str) -> dict:
    """Send a probe through one route so the user can verify it before a campaign."""
    contact = Contact(email=to_addr, first_name="Test", unsubscribe_token="test-token")
    try:
        deliver(
            sender, contact,
            f"Test from {sender.name}",
            "<p>This is a test send from your campaign sender.</p>"
            "<p>If it arrived, this route is configured correctly.</p>",
            True,
        )
    except SendError as exc:
        CampaignSender.objects.filter(pk=sender.pk).update(last_error=str(exc))
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - surface anything the driver didn't wrap
        CampaignSender.objects.filter(pk=sender.pk).update(last_error=str(exc))
        return {"ok": False, "error": str(exc)}
    CampaignSender.objects.filter(pk=sender.pk).update(last_error="")
    return {"ok": True, "detail": f"Test sent to {to_addr}"}
