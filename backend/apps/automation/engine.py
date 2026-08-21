"""The automation engine: poll mailboxes, match rules, send scheduled replies.

Uses only the Python standard library for mail (imaplib/smtplib), so there are no
extra runtime dependencies. Designed to be called on a loop by the `run_engine`
management command (or a cron/systemd timer).
"""
from __future__ import annotations

import email
import imaplib
import re
import secrets
import smtplib
import string
from datetime import timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage as PyEmailMessage
from email.utils import parseaddr
from html import unescape

from django.db.models import Min, Q
from django.utils import timezone

from apps.automation.models import Config
from apps.billing.services import workspace_can_send
from apps.mail.models import EmailMessage, normalize_subject
from apps.mailboxes.models import Mailbox
from apps.notifications.telegram import notify
from apps.proxies.models import Proxy
from apps.proxies.net import open_smtp
from apps.rules.models import Placeholder, Rule
from apps.security.models import SystemEvent


# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #
def _imap_connect(mailbox: Mailbox) -> imaplib.IMAP4:
    if mailbox.imap_use_ssl:
        conn = imaplib.IMAP4_SSL(mailbox.imap_host, mailbox.imap_port)
    else:
        conn = imaplib.IMAP4(mailbox.imap_host, mailbox.imap_port)
    conn.login(mailbox.username, mailbox.password)
    return conn


def test_connection(mailbox: Mailbox) -> dict:
    """Verify IMAP login and SMTP login without sending anything."""
    result = {"imap": False, "smtp": False, "error": ""}
    try:
        conn = _imap_connect(mailbox)
        conn.select("INBOX", readonly=True)
        conn.logout()
        result["imap"] = True
    except Exception as exc:  # noqa: BLE001 - report any failure to the UI
        result["error"] = f"IMAP: {exc}"
        return result
    try:
        smtp = _smtp_connect(mailbox)
        smtp.quit()
        result["smtp"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"SMTP: {exc}"
    return result


def _smtp_connect(mailbox: Mailbox) -> smtplib.SMTP:
    """Open an authenticated SMTP connection.

    When the mailbox has `use_proxy` on, route through a random active proxy from
    the workspace pool, retrying a few others on failure. If proxies are configured
    but all fail we raise (rather than silently leaking the server's direct IP); if
    the pool is empty we fall back to a direct connection so mail still flows.
    """
    if not mailbox.use_proxy:
        return open_smtp(mailbox, None)

    tried: list[int] = []
    last_exc: Exception | None = None
    for _ in range(3):
        proxy = Proxy.pick_random(mailbox.workspace, exclude_ids=tried)
        if proxy is None:
            break
        try:
            smtp = open_smtp(mailbox, proxy)
            proxy.mark_ok()
            return smtp
        except Exception as exc:  # noqa: BLE001 - try the next proxy in the pool
            proxy.mark_failed(str(exc))
            tried.append(proxy.id)
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    return open_smtp(mailbox, None)


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _decode(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _is_auto_message(msg: email.message.Message, from_addr: str) -> bool:
    """Detect auto-responders / bulk mail so we never auto-reply to them.

    Replying to another auto-responder (or a mailing list / bounce) creates a mail
    loop, so we record the message but skip scheduling a reply. Follows RFC 3834.
    """
    auto = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in {"bulk", "list", "junk", "auto_reply"}:
        return True
    if msg.get("List-Id") or msg.get("List-Unsubscribe"):
        return True
    local = (from_addr or "").split("@")[0].strip().lower()
    if local in {"mailer-daemon", "postmaster", "no-reply", "noreply", "do-not-reply", "donotreply"}:
        return True
    return False


def html_to_text(html: str) -> str:
    """Flatten an HTML body into a readable plain-text alternative.

    Every HTML reply ships a text/plain part alongside it (RFC 2046 multipart/
    alternative), both because some clients refuse HTML and because a missing text
    part is a well-known spam signal. This is deliberately dependency-free: it keeps
    block structure as line breaks and drops everything else.
    """
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition")
            ):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        # Fall back to HTML stripped of tags.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(msg.get_content_charset() or "utf-8", "replace")
    return ""


# --------------------------------------------------------------------------- #
# Template rendering
# --------------------------------------------------------------------------- #
# Random-string placeholders: {{ran_letter_10}} -> 10 random letters, resolved
# freshly on every render so each sent email differs. The alphabet is chosen by the
# middle word; the trailing number is the length (capped so a typo can't blow up a mail).
_RANDOM_ALPHABETS = {
    "letter": string.ascii_letters,
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digit": string.digits,
    "number": string.digits,
    "alnum": string.ascii_letters + string.digits,
    "hex": "0123456789abcdef",
}
_RANDOM_KEY = re.compile(r"^ran_(letter|lower|upper|digit|number|alnum|hex)_(\d{1,3})$")
_RANDOM_MAX_LEN = 256


def _random_token(key: str):
    """Return a random string for a ran_<kind>_<n> key, or None if it isn't one.

    Uses `secrets` (CSPRNG), so tokens are unguessable — fine to use as one-time
    codes or cache-busters, not just filler.
    """
    m = _RANDOM_KEY.match(key)
    if not m:
        return None
    alphabet = _RANDOM_ALPHABETS[m.group(1)]
    length = min(int(m.group(2)), _RANDOM_MAX_LEN)
    return "".join(secrets.choice(alphabet) for _ in range(length))


def render_template(text: str, context: dict, workspace=None) -> str:
    """Replace {{key}} tokens using dynamic context + the workspace's Placeholders.

    Also supports {{ran_letter_N}} / ran_digit_N / ran_alnum_N / ran_hex_N etc.,
    each resolved to a fresh random string of length N at render time.
    """
    values = dict(context)
    placeholders = Placeholder.objects.filter(workspace=workspace) if workspace else Placeholder.objects.none()
    for ph in placeholders:
        values.setdefault(ph.key, ph.static_value)

    def repl(match: re.Match) -> str:
        key = match.group(1).strip()
        token = _random_token(key)
        if token is not None:
            return token
        return str(values.get(key, match.group(0)))

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", repl, text or "")


# --------------------------------------------------------------------------- #
# Per-account timing
# --------------------------------------------------------------------------- #
# Each mailbox may set its own cadence; a blank override falls back to the
# workspace Config, so accounts added before these fields existed are unaffected.

# A tick rarely lands exactly on the interval, so without a little slack a mailbox
# on a 30s interval polled by a 30s loop would drift to every other tick.
POLL_TOLERANCE_SECONDS = 1


def effective_poll_interval(mailbox: Mailbox, config: Config | None = None) -> int:
    if mailbox.poll_interval_seconds:
        return mailbox.poll_interval_seconds
    return (config or Config.load(mailbox.workspace)).poll_interval_seconds


def effective_reply_delay(mailbox: Mailbox, config: Config) -> int:
    # `is not None` rather than truthiness: 0 minutes is a valid "reply at once".
    if mailbox.reply_delay_minutes is not None:
        return mailbox.reply_delay_minutes
    return config.reply_delay_minutes


def is_due_for_poll(mailbox: Mailbox, config: Config, now=None) -> bool:
    if not mailbox.last_polled_at:
        return True
    elapsed = ((now or timezone.now()) - mailbox.last_polled_at).total_seconds()
    return elapsed >= effective_poll_interval(mailbox, config) - POLL_TOLERANCE_SECONDS


def next_tick_seconds() -> int:
    """How long the engine loop should sleep: the shortest cadence in use."""
    intervals = [
        effective_poll_interval(m)
        for m in Mailbox.objects.filter(is_active=True).select_related("workspace")
    ]
    if not intervals:
        intervals = [Config.objects.aggregate(m=Min("poll_interval_seconds"))["m"] or 30]
    return max(5, min(intervals))


# --------------------------------------------------------------------------- #
# Polling
# --------------------------------------------------------------------------- #
def poll_mailbox(mailbox: Mailbox) -> int:
    """Fetch new incoming messages, record them, and schedule any auto-replies.

    Returns the number of new messages ingested.
    """
    config = Config.load(mailbox.workspace)
    ingested = 0
    conn = _imap_connect(mailbox)
    try:
        conn.select("INBOX")
        # UIDs greater than the last one we've seen = new since last poll.
        criterion = f"UID {mailbox.last_seen_uid + 1}:*" if mailbox.last_seen_uid else "ALL"
        typ, data = conn.uid("search", None, criterion)
        if typ != "OK" or not data or not data[0]:
            return 0
        uids = [int(u) for u in data[0].split()]
        # On a very first run (ALL), avoid replaying the whole history — only take
        # the newest handful so the client isn't spammed with replies to old mail.
        if not mailbox.last_seen_uid:
            uids = uids[-10:]

        for uid in uids:
            if uid <= mailbox.last_seen_uid:
                continue
            typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            ingested += _ingest_incoming(mailbox, uid, msg, config)
            mailbox.last_seen_uid = max(mailbox.last_seen_uid, uid)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    mailbox.last_polled_at = timezone.now()
    mailbox.last_error = ""
    mailbox.save(update_fields=["last_seen_uid", "last_polled_at", "last_error"])
    return ingested


def _ingest_incoming(mailbox: Mailbox, uid: int, msg, config: Config) -> int:
    message_id = (msg.get("Message-ID") or "").strip()
    # De-dupe within this workspace's mail (same Message-ID could legitimately land in
    # two different users' mailboxes).
    if message_id and EmailMessage.objects.filter(message_id=message_id, workspace=mailbox.workspace).exists():
        return 0

    subject = _decode(msg.get("Subject", ""))
    from_addr = parseaddr(_decode(msg.get("From", "")))[1]
    body = _extract_body(msg)
    thread_key = normalize_subject(subject)

    # Link back to the sent email this is replying to, matched by subject thread.
    original = (
        EmailMessage.objects.filter(
            mailbox=mailbox, direction=EmailMessage.Direction.OUTGOING, thread_key=thread_key
        )
        .order_by("-created_at")
        .first()
    )

    incoming = EmailMessage.objects.create(
        workspace=mailbox.workspace,
        mailbox=mailbox,
        direction=EmailMessage.Direction.INCOMING,
        status=EmailMessage.Status.RECEIVED,
        message_id=message_id,
        in_reply_to=(msg.get("In-Reply-To") or "").strip(),
        imap_uid=uid,
        subject=subject,
        thread_key=thread_key,
        from_addr=from_addr,
        to_addr=mailbox.email_address,
        body=body[:20000],
        reply_to_message=original,
        received_at=timezone.now(),
    )

    notify(mailbox.workspace, "received", f"📥 <b>{mailbox.name}</b> received:\n{subject}\nfrom {from_addr}")
    if config.auto_reply_enabled and not _is_auto_message(msg, from_addr):
        _maybe_schedule_reply(mailbox, incoming, config)
    return 1


def _maybe_schedule_reply(mailbox: Mailbox, incoming: EmailMessage, config: Config):
    # Only the mailbox workspace's own rules can fire.
    rules = (
        Rule.objects.filter(is_active=True, workspace=mailbox.workspace)
        .filter(Q(mailboxes=mailbox) | Q(mailboxes__isnull=True))
        .distinct()
        .select_related("template")
        .order_by("priority", "name")
    )
    for rule in rules:
        if not rule.matches(incoming.subject):
            continue
        template = rule.template
        if not template.is_active:
            continue
        context = {
            "sender_name": incoming.from_addr.split("@")[0].replace(".", " ").title(),
            "sender_email": incoming.from_addr,
            "original_subject": incoming.subject,
            "mailbox_name": mailbox.name,
            "date": timezone.now().strftime("%A, %B %d, %Y"),
        }
        subject = render_template(template.subject, context, workspace=mailbox.workspace)
        body = render_template(template.body, context, workspace=mailbox.workspace)
        if config.signature:
            # Two newlines read as a blank line in text, but collapse to nothing in
            # HTML — there the separator has to be markup.
            if template.is_html:
                body = f"{body}<br><br>{config.signature.replace(chr(10), '<br>')}"
            else:
                body = f"{body}\n\n{config.signature}"

        reply = EmailMessage.objects.create(
            workspace=mailbox.workspace,
            mailbox=mailbox,
            direction=EmailMessage.Direction.OUTGOING,
            status=EmailMessage.Status.SCHEDULED,
            subject=subject,
            thread_key=normalize_subject(subject),
            from_addr=mailbox.email_address,
            to_addr=incoming.from_addr,
            body=body,
            is_html=template.is_html,
            matched_rule=rule,
            reply_to_message=incoming,
            scheduled_for=timezone.now() + timedelta(minutes=effective_reply_delay(mailbox, config)),
        )
        attachments = list(rule.attachments.all())
        if attachments:
            reply.attachments.set(attachments)
        SystemEvent.log("engine", f"Scheduled reply to {incoming.from_addr} via rule '{rule.name}'",
                        workspace=mailbox.workspace)
        return  # first matching rule wins


# --------------------------------------------------------------------------- #
# Sending scheduled replies
# --------------------------------------------------------------------------- #
def send_due_replies(workspace=None) -> int:
    """Send any scheduled outgoing messages whose delay has elapsed.

    Pass ``workspace`` to restrict sending to a single workspace (the on-demand run).
    """
    now = timezone.now()
    due = EmailMessage.objects.filter(
        direction=EmailMessage.Direction.OUTGOING,
        status=EmailMessage.Status.SCHEDULED,
        scheduled_for__lte=now,
    ).select_related("mailbox")
    if workspace is not None:
        due = due.filter(workspace=workspace)

    sent = 0
    for message in due:
        # Respect toggles that may have flipped after the reply was scheduled.
        if not message.mailbox.is_active or not Config.load(message.workspace).auto_reply_enabled:
            continue
        # Paywall (sending only): if the workspace owner's subscription has lapsed,
        # leave the reply scheduled — it goes out once they pay, nothing is lost.
        if not workspace_can_send(message.workspace):
            continue
        try:
            _send_message(message)
            message.status = EmailMessage.Status.SENT
            message.sent_at = timezone.now()
            message.error = ""
            sent += 1
            notify(message.workspace, "sent", f"📤 <b>{message.mailbox.name}</b> sent reply:\n{message.subject}\nto {message.to_addr}")
            SystemEvent.log("engine", f"Sent reply to {message.to_addr}", "success", workspace=message.workspace)
        except Exception as exc:  # noqa: BLE001
            message.status = EmailMessage.Status.FAILED
            message.error = str(exc)
            notify(message.workspace, "error", f"⚠️ Failed to send reply to {message.to_addr}: {exc}")
            SystemEvent.log("engine", f"Send failed to {message.to_addr}: {exc}", "error", workspace=message.workspace)
        message.save(update_fields=["status", "sent_at", "error"])
    return sent


def _send_message(message: EmailMessage):
    mailbox = message.mailbox
    py = PyEmailMessage()
    py["From"] = mailbox.email_address
    py["To"] = message.to_addr
    py["Subject"] = message.subject
    # Mark as an automatic reply so well-behaved responders don't reply back (RFC 3834).
    py["Auto-Submitted"] = "auto-replied"
    if message.reply_to_message and message.reply_to_message.message_id:
        py["In-Reply-To"] = message.reply_to_message.message_id
        py["References"] = message.reply_to_message.message_id
    if message.is_html:
        # set_content first makes text/plain the fallback part; add_alternative then
        # appends the HTML, and clients pick the last part they can render.
        py.set_content(html_to_text(message.body))
        py.add_alternative(message.body, subtype="html")
    else:
        py.set_content(message.body)

    for att in message.attachments.all():
        try:
            att.file.open("rb")
            data = att.file.read()
            att.file.close()
            maintype, _, subtype = (att.content_type or "application/octet-stream").partition("/")
            py.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                              filename=att.file.name.split("/")[-1])
        except Exception:  # noqa: BLE001 - skip a missing file rather than fail the whole send
            continue

    smtp = _smtp_connect(mailbox)
    try:
        smtp.send_message(py)
    finally:
        smtp.quit()


def run_once(workspace=None, force=False) -> dict:
    """One full engine tick: poll due mailboxes, then send due replies.

    Pass ``workspace`` to restrict the tick to a single workspace (the on-demand run
    from the dashboard); the looping ``run_engine`` command leaves it ``None`` to
    process every workspace. ``force`` polls every mailbox regardless of its own
    interval — what a human pressing "Run now" expects.
    """
    stats = {"polled": 0, "skipped": 0, "ingested": 0, "sent": 0, "errors": []}
    now = timezone.now()
    mailboxes = Mailbox.objects.filter(is_active=True).select_related("workspace")
    if workspace is not None:
        mailboxes = mailboxes.filter(workspace=workspace)
    for mailbox in mailboxes:
        # The loop ticks at the shortest interval in use, so a mailbox on a slower
        # cadence simply isn't due on most ticks.
        if not force and not is_due_for_poll(mailbox, Config.load(mailbox.workspace), now):
            stats["skipped"] += 1
            continue
        try:
            stats["ingested"] += poll_mailbox(mailbox)
            stats["polled"] += 1
        except Exception as exc:  # noqa: BLE001
            mailbox.last_error = str(exc)
            mailbox.save(update_fields=["last_error"])
            stats["errors"].append(f"{mailbox.name}: {exc}")
            notify(mailbox.workspace, "error", f"⚠️ Mailbox <b>{mailbox.name}</b> poll error: {exc}")
            SystemEvent.log("mailbox", f"Poll error on {mailbox.name}: {exc}", "error", workspace=mailbox.workspace)
    stats["sent"] = send_due_replies(workspace=workspace)
    return stats
