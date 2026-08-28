"""The automation engine: poll mailboxes, match rules, send scheduled replies.

Uses only the Python standard library for mail (imaplib/smtplib), so there are no
extra runtime dependencies. Designed to be called on a loop by the `run_engine`
management command (or a cron/systemd timer).
"""
from __future__ import annotations

import email
import hashlib
import imaplib
import re
import secrets
import smtplib
import ssl
import string
import uuid as uuid_mod
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
# 993 is implicit TLS, 143 is plaintext-then-STARTTLS — the same split as SMTP's
# 465/587, and the same hang if the two are mismatched.
IMAP_IMPLICIT_TLS_PORTS = {993}


def _imap_connect(mailbox: Mailbox) -> imaplib.IMAP4:
    port = int(mailbox.imap_port or 993)
    # The port decides, not the checkbox: a 993 mailbox saved with SSL off used to
    # open a plaintext socket against a TLS listener and stall until timeout.
    if mailbox.imap_use_ssl or port in IMAP_IMPLICIT_TLS_PORTS:
        conn = imaplib.IMAP4_SSL(mailbox.imap_host, port)
    else:
        conn = imaplib.IMAP4(mailbox.imap_host, port)
        # Upgrade an explicit-TLS port when the server offers it, so a mailbox on
        # 143 is not left sending its password in the clear.
        if "STARTTLS" in conn.capabilities:
            conn.starttls(ssl.create_default_context())
    conn.login(mailbox.username, mailbox.password)
    return conn


def _diagnose(exc: Exception, host: str, port: int, kind: str) -> str:
    """Turn a raw socket/protocol error into something a user can act on.

    A wrong TLS port produces a bare timeout, which tells the user nothing — this
    is where they get told to try the other port instead.
    """
    text = str(exc) or type(exc).__name__
    low = text.lower()
    ssl_ports = {"smtp": 465, "imap": 993}
    tls_ports = {"smtp": 587, "imap": 143}
    if "timed out" in low or "unexpectedly closed" in low or isinstance(exc, TimeoutError):
        if port == tls_ports[kind]:
            return (f"{text} — no reply from {host}:{port}. If your provider lists port "
                    f"{ssl_ports[kind]} for {kind.upper()}, use that instead.")
        return (f"{text} — no reply from {host}:{port}. Check the host name is right and "
                f"that your provider allows {kind.upper()} access for this mailbox.")
    if "authentication" in low or "auth" in low or "login" in low or "credentials" in low:
        return (f"{text} — the server was reached, so the host and port are right; it "
                f"rejected the username or password. Providers with 2-factor sign-in "
                f"usually need an app password rather than the normal one.")
    if "certificate" in low or "ssl" in low:
        return f"{text} — TLS problem talking to {host}:{port}. Check the port matches your provider's."
    if "name or service not known" in low or "nodename" in low or "getaddrinfo" in low:
        return f"{text} — the host name {host} could not be found. Check it for typos."
    return f"{text} (at {host}:{port})"


def test_connection(mailbox: Mailbox) -> dict:
    """Verify IMAP login and SMTP login without sending anything."""
    result = {"imap": False, "smtp": False, "folders": [], "error": ""}
    try:
        conn = _imap_connect(mailbox)
        try:
            # Surfacing the folder list here is how a user confirms we actually
            # found their Spam folder, without waiting for a poll to prove it.
            result["folders"] = folders_to_poll(mailbox, conn)
            conn.select("INBOX", readonly=True)
        finally:
            conn.logout()
        result["imap"] = True
    except Exception as exc:  # noqa: BLE001 - report any failure to the UI
        result["error"] = "IMAP: " + _diagnose(exc, mailbox.imap_host, int(mailbox.imap_port or 993), "imap")
        return result
    try:
        smtp = _smtp_connect(mailbox)
        smtp.quit()
        result["smtp"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = "SMTP: " + _diagnose(exc, mailbox.smtp_host, int(mailbox.smtp_port or 587), "smtp")
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


# Date-offset placeholders: {{date_plus_3}} -> three days out, {{date_minus_1}} -> yesterday,
# and {{business_day_plus_2}} which skips weekends — the usual shape of an SLA promise
# ("we'll get back to you by ..."). Resolved at render time, like the random tokens.
_DATE_OFFSET_KEY = re.compile(r"^(date|business_day)_(plus|minus)_(\d{1,4})$")
_DATE_OFFSET_MAX_DAYS = 3650
_LONG_DATE = "%A, %B %d, %Y"


def _date_token(key: str):
    """Return a formatted date for a date_plus_N / business_day_plus_N key, else None."""
    m = _DATE_OFFSET_KEY.match(key)
    if not m:
        return None
    kind, direction, raw = m.groups()
    days = min(int(raw), _DATE_OFFSET_MAX_DAYS)
    step = timedelta(days=1 if direction == "plus" else -1)
    when = timezone.localtime()
    if kind == "business_day":
        # Step day by day and only count weekdays, so "2 business days" from a Friday
        # lands on Tuesday instead of Sunday.
        remaining = days
        while remaining > 0:
            when += step
            if when.weekday() < 5:
                remaining -= 1
    else:
        when += step * days
    return when.strftime(_LONG_DATE)


# normalize_subject() lowercases because it is a thread-matching key; a subject shown
# back to the recipient must keep its original capitalisation, so strip prefixes here.
_SUBJECT_PREFIX = re.compile(r"^\s*(re|fwd?|aw|sv)\s*(\[\d+\])?\s*:\s*", re.IGNORECASE)


def _clean_subject(subject: str) -> str:
    """'RE: Fwd: New warehouse build' -> 'New warehouse build' (case preserved)."""
    subject = (subject or "").strip()
    prev = None
    while prev != subject:
        prev = subject
        subject = _SUBJECT_PREFIX.sub("", subject)
    return re.sub(r"\s+", " ", subject).strip()


def _split_email(addr: str) -> tuple[str, str]:
    """'jane.doe@acme.com' -> ('jane.doe', 'acme.com'). Tolerant of blanks/garbage."""
    local, _, domain = (addr or "").strip().partition("@")
    return local, domain


def _greeting(when) -> str:
    hour = when.hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


# A quoted original can be arbitrarily long; cap it so one huge thread can't bloat
# every reply that quotes it.
_QUOTE_MAX_CHARS = 5000


def build_context(incoming: EmailMessage, mailbox: Mailbox, rule=None, template=None) -> dict:
    """Every {{token}} the engine resolves when rendering a reply.

    Single source of truth: the live send path calls this directly and the template
    preview endpoint calls it via `sample_context`, so what a user previews is exactly
    what goes out. Adding a token here makes it available in both.
    """
    now = timezone.localtime()
    received = timezone.localtime(incoming.received_at) if incoming.received_at else now

    sender_name = _sender_name(incoming)
    first, _, last = sender_name.partition(" ")
    sender_user, sender_domain = _split_email(incoming.from_addr)

    mailbox_email = mailbox.email_address if mailbox else ""
    _, mailbox_domain = _split_email(mailbox_email)

    # An unsaved Mailbox (the preview path) has no workspace; don't trip on it.
    workspace = mailbox.workspace if mailbox is not None and getattr(mailbox, "workspace_id", None) else None

    body = incoming.body or ""
    quoted = "\n".join("> " + line for line in body[:_QUOTE_MAX_CHARS].splitlines())

    # Stable per-thread reference: same message always yields the same ticket id,
    # so a retried or re-rendered reply doesn't invent a new one.
    seed = incoming.message_id or f"msg-{incoming.pk}"
    ticket_id = hashlib.sha1(seed.encode("utf-8", "replace")).hexdigest()[:8].upper()

    return {
        # --- Who wrote in --------------------------------------------------
        "sender_name": sender_name,
        "sender_first_name": first or sender_name,
        "sender_last_name": last,
        "sender_email": incoming.from_addr or "",
        "sender_user": sender_user,
        "sender_domain": sender_domain,
        # --- Which mailbox is answering ------------------------------------
        "mailbox_name": (mailbox.name if mailbox else ""),
        "mailbox_email": mailbox_email,
        "mailbox_domain": mailbox_domain,
        "workspace_name": (workspace.name if workspace else ""),
        # --- The message being answered ------------------------------------
        "original_subject": incoming.subject or "",
        "subject_clean": _clean_subject(incoming.subject),
        "original_body": body[:_QUOTE_MAX_CHARS],
        "quoted_body": quoted,
        "message_id": incoming.message_id or "",
        "ticket_id": ticket_id,
        "received_date": received.strftime(_LONG_DATE),
        "received_time": received.strftime("%I:%M %p").lstrip("0"),
        # --- Right now -----------------------------------------------------
        "date": now.strftime(_LONG_DATE),
        "date_short": now.strftime("%Y-%m-%d"),
        "date_us": now.strftime("%m/%d/%Y"),
        "date_eu": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%I:%M %p").lstrip("0"),
        "time_24": now.strftime("%H:%M"),
        "datetime": now.strftime(f"{_LONG_DATE} at %I:%M %p").replace(" at 0", " at "),
        "day": now.strftime("%d"),
        "day_name": now.strftime("%A"),
        "month": now.strftime("%m"),
        "month_name": now.strftime("%B"),
        "year": now.strftime("%Y"),
        "timezone": now.tzname() or "",
        "greeting": _greeting(now),
        # --- Which automation fired ----------------------------------------
        "rule_name": (rule.name if rule else ""),
        "template_name": (template.name if template else ""),
        # --- One-off identifier --------------------------------------------
        "uuid": str(uuid_mod.uuid4()),
    }


def sample_context() -> dict:
    """Realistic stand-in values for the template preview endpoint.

    Built from unsaved model instances through `build_context`, so preview can never
    advertise a token the real send path doesn't resolve.
    """
    incoming = EmailMessage(
        subject="Re: Project Inquiry: New warehouse build",
        from_addr="jane.doe@example.com",
        from_name="Jane Doe",
        body="Hello,\n\nCould you send a quote for the new warehouse build?\n\nThanks,\nJane",
        message_id="<sample-preview@example.com>",
        received_at=timezone.now(),
    )
    mailbox = Mailbox(name="Sales inbox", email_address="sales@your-domain.com")
    context = build_context(incoming, mailbox)
    context["workspace_name"] = "Your workspace"
    context["rule_name"] = "Project inquiries"
    context["template_name"] = "Standard reply"
    return context


def render_template(text: str, context: dict, workspace=None) -> str:
    """Replace {{key}} tokens using dynamic context + the workspace's Placeholders.

    Also supports the computed tokens resolved at render time:
    {{ran_letter_N}} / ran_digit_N / ran_alnum_N / ran_hex_N (fresh random strings),
    and {{date_plus_N}} / {{date_minus_N}} / {{business_day_plus_N}} (offset dates).
    """
    values = dict(context)
    placeholders = Placeholder.objects.filter(workspace=workspace) if workspace else Placeholder.objects.none()
    for ph in placeholders:
        values.setdefault(ph.key, ph.static_value)

    def repl(match: re.Match) -> str:
        key = match.group(1).strip()
        token = _random_token(key)
        if token is None:
            token = _date_token(key)
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
# Folder discovery
# --------------------------------------------------------------------------- #
# IMAP never standardised a name for the spam folder: Gmail uses "[Gmail]/Spam"
# (localised on non-English accounts), Yahoo "Bulk Mail", Outlook "Junk", others
# "Spam" or "Junk E-mail". So we look for the RFC 6154 \Junk special-use flag first —
# servers set it whatever the display name — and only fall back to matching known
# names for servers too old to advertise special-use.
_SPAM_FLAGS = {"\\junk", "\\spam"}
_SPAM_NAMES = {
    "spam", "junk", "junk mail", "junkmail", "junk e-mail", "junk email",
    "bulk", "bulk mail", "[gmail]/spam", "[google mail]/spam",
    "inbox.spam", "inbox.junk", "inbox/spam", "inbox/junk",
}
# Never poll these, even if a name heuristic matches: ingesting our own sent mail
# or a trashed/archived copy would re-reply to threads that are already handled.
_SKIP_FLAGS = {"\\sent", "\\drafts", "\\trash", "\\all", "\\archive", "\\noselect"}

# A LIST response line: (\HasNoChildren \Junk) "/" "[Gmail]/Spam"
_LIST_LINE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?:"(?:[^"]*)"|NIL)\s+(?P<name>.*)$')

# How many messages to take the first time a folder is polled. Without this, a new
# mailbox would replay its entire history and reply to years-old mail.
FIRST_RUN_LIMIT = 10


def _list_folders(conn) -> list[tuple[str, set[str]]]:
    """Return [(folder_name, lowercased_flags)] for every folder on the account."""
    typ, data = conn.list()
    if typ != "OK" or not data:
        return []
    folders = []
    for item in data:
        if not item:
            continue
        # A name sent as an IMAP literal arrives as (header_bytes, name_bytes).
        if isinstance(item, tuple):
            line, literal = item[0], item[1]
        else:
            line, literal = item, None
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        match = _LIST_LINE.match(line.strip())
        if not match:
            continue
        flags = {f.lower() for f in match.group("flags").split()}
        if literal is not None:
            name = literal.decode("utf-8", "replace")
        else:
            name = match.group("name").strip().strip('"')
        if name:
            folders.append((name, flags))
    return folders


def detect_spam_folders(conn) -> list[str]:
    """Find the account's spam folder(s), by special-use flag then by name."""
    by_flag, by_name = [], []
    for name, flags in _list_folders(conn):
        if flags & _SKIP_FLAGS:
            continue
        if flags & _SPAM_FLAGS:
            by_flag.append(name)
        elif name.lower() in _SPAM_NAMES:
            by_name.append(name)
    # A flagged folder is authoritative; the name list is only a fallback.
    return by_flag or by_name


def folders_to_poll(mailbox: Mailbox, conn) -> list[str]:
    """INBOX first, then the spam folder(s), then any manual extras for this account."""
    folders = ["INBOX"]
    if mailbox.scan_spam:
        try:
            folders += detect_spam_folders(conn)
        except Exception as exc:  # noqa: BLE001 - a failed LIST must never cost us INBOX
            SystemEvent.log("mailbox", f"Could not list folders on {mailbox.name}: {exc}",
                            "warning", workspace=mailbox.workspace)
    folders += mailbox.extra_folder_list

    seen, ordered = set(), []
    for folder in folders:
        if folder.lower() not in seen:
            seen.add(folder.lower())
            ordered.append(folder)
    return ordered


def _quote_folder(folder: str) -> str:
    """Quote a mailbox name for SELECT — names like "Bulk Mail" contain spaces."""
    return '"%s"' % folder.replace("\\", "\\\\").replace('"', '\\"')


def _uidvalidity(conn) -> int:
    """The UIDVALIDITY of the currently selected folder, or 0 if unreported."""
    typ, data = conn.response("UIDVALIDITY")
    if data and data[0]:
        try:
            return int(data[0])
        except (TypeError, ValueError):
            pass
    return 0


# --------------------------------------------------------------------------- #
# Polling
# --------------------------------------------------------------------------- #
def poll_mailbox(mailbox: Mailbox) -> int:
    """Fetch new incoming messages from every watched folder, record them, and
    schedule any auto-replies.

    Returns the number of new messages ingested.
    """
    config = Config.load(mailbox.workspace)
    cursors = dict(mailbox.folder_cursors or {})
    # Mailboxes from before per-folder cursors only tracked INBOX, in last_seen_uid;
    # seeding from it stops the first multi-folder poll replaying the inbox.
    if "INBOX" not in cursors and mailbox.last_seen_uid:
        cursors["INBOX"] = {"uid": mailbox.last_seen_uid}

    ingested = 0
    folder_errors: list[str] = []
    conn = _imap_connect(mailbox)
    try:
        for folder in folders_to_poll(mailbox, conn):
            try:
                ingested += _poll_folder(mailbox, conn, folder, cursors, config)
            except Exception as exc:  # noqa: BLE001
                # INBOX failing means the mailbox itself is broken — let run_once
                # record and alert on it. A secondary folder that's gone, renamed or
                # unreadable is not worth losing the rest of the poll over.
                if folder.upper() == "INBOX":
                    raise
                folder_errors.append(f"{folder}: {exc}")
                SystemEvent.log("mailbox", f"Skipped folder '{folder}' on {mailbox.name}: {exc}",
                                "warning", workspace=mailbox.workspace)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass

    mailbox.folder_cursors = cursors
    mailbox.last_seen_uid = int((cursors.get("INBOX") or {}).get("uid") or 0)
    mailbox.last_polled_at = timezone.now()
    mailbox.last_error = "; ".join(folder_errors)
    mailbox.save(update_fields=["last_seen_uid", "folder_cursors", "last_polled_at", "last_error"])
    return ingested


def _poll_folder(mailbox: Mailbox, conn, folder: str, cursors: dict, config: Config) -> int:
    """Ingest everything new in one folder, advancing that folder's cursor."""
    typ, _ = conn.select(_quote_folder(folder))
    if typ != "OK":
        raise RuntimeError(f"SELECT failed ({typ})")

    state = cursors.get(folder) or {}
    last_uid = int(state.get("uid") or 0)
    uidvalidity = _uidvalidity(conn)
    # A changed UIDVALIDITY means the server renumbered the folder, so our stored UID
    # now points at nothing (RFC 3501 §2.3.1.1) — safer to restart than to skip mail.
    if uidvalidity and state.get("uidvalidity") not in (None, uidvalidity):
        last_uid = 0

    # UIDs greater than the last one we've seen = new since last poll.
    criterion = f"UID {last_uid + 1}:*" if last_uid else "ALL"
    typ, data = conn.uid("search", None, criterion)
    if typ != "OK":
        raise RuntimeError(f"SEARCH failed ({typ})")
    uids = [int(u) for u in data[0].split()] if data and data[0] else []
    if not last_uid:
        uids = uids[-FIRST_RUN_LIMIT:]

    ingested = 0
    highest = last_uid
    for uid in uids:
        # "UID n:*" always returns the highest UID even when it is below n.
        if uid <= last_uid:
            continue
        typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        ingested += _ingest_incoming(mailbox, uid, msg, config, folder)
        highest = max(highest, uid)

    cursors[folder] = {"uid": highest, "uidvalidity": uidvalidity}
    return ingested


def _ingest_incoming(mailbox: Mailbox, uid: int, msg, config: Config, folder: str = "INBOX") -> int:
    message_id = (msg.get("Message-ID") or "").strip()
    # De-dupe within this workspace's mail (same Message-ID could legitimately land in
    # two different users' mailboxes). This is also what keeps a message filed in both
    # INBOX and Spam — or moved between them between polls — from being replied to twice.
    if message_id and EmailMessage.objects.filter(message_id=message_id, workspace=mailbox.workspace).exists():
        return 0

    subject = _decode(msg.get("Subject", ""))
    from_name, from_addr = parseaddr(_decode(msg.get("From", "")))
    from_name = from_name.strip()
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
        folder=folder,
        subject=subject,
        thread_key=thread_key,
        from_addr=from_addr,
        from_name=from_name,
        to_addr=mailbox.email_address,
        body=body[:20000],
        reply_to_message=original,
        received_at=timezone.now(),
    )

    # Call out the folder when it isn't the inbox — "this one was in Spam" is exactly
    # what the user needs to know from the alert.
    where = "" if folder.upper() == "INBOX" else f" in {folder}"
    notify(mailbox.workspace, "received",
           f"📥 <b>{mailbox.name}</b> received{where}:\n{subject}\nfrom {from_addr}")
    if config.auto_reply_enabled and not _is_auto_message(msg, from_addr):
        _maybe_schedule_reply(mailbox, incoming, config)
    return 1


def _sender_name(incoming: EmailMessage) -> str:
    """A human name for {{sender_name}}: the From display name if it's a real name,
    otherwise the email's local part cleaned up (jane.doe -> Jane Doe)."""
    name = (incoming.from_name or "").strip().strip('"').strip()
    # Some senders put their own address in the display-name slot; that's not a name.
    if name and "@" not in name:
        return name
    local = (incoming.from_addr or "").split("@")[0]
    return re.sub(r"[._-]+", " ", local).strip().title() or "there"


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
        context = build_context(incoming, mailbox, rule=rule, template=template)
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
# Send-retry policy. A transient SMTP failure — greylisting, a rate-limit blip, a
# dropped TLS connection — shouldn't lose a reply, which for a marketing app is the
# reply a client is waiting on. So a failed send is re-queued with growing backoff
# and only marked FAILED (and alerted loudly) once SEND_MAX_ATTEMPTS is spent.
SEND_MAX_ATTEMPTS = 5
_RETRY_BACKOFF_SECONDS = [60, 300, 900, 1800, 3600]  # 1m, 5m, 15m, 30m, 60m


def _retry_delay(attempt: int) -> timedelta:
    idx = min(max(attempt - 1, 0), len(_RETRY_BACKOFF_SECONDS) - 1)
    return timedelta(seconds=_RETRY_BACKOFF_SECONDS[idx])


def send_due_replies(workspace=None) -> int:
    """Send scheduled outgoing messages whose delay has elapsed.

    Transient failures are retried with backoff (see SEND_MAX_ATTEMPTS); a message
    is due when its schedule time has passed AND it isn't waiting on a retry delay.
    Pass ``workspace`` to restrict sending to a single workspace (the on-demand run).
    """
    now = timezone.now()
    due = (
        EmailMessage.objects.filter(
            direction=EmailMessage.Direction.OUTGOING,
            status=EmailMessage.Status.SCHEDULED,
            scheduled_for__lte=now,
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .select_related("mailbox")
    )
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
        # Mailbox out of daily quota and nothing to fall back to: leave the reply
        # scheduled rather than spending its retries. The cap resets at midnight and
        # it goes out then — the same "pause, don't lose" rule as the paywall.
        if (not message.mailbox.has_send_quota()
                and _reply_fallback_route(message.workspace, message.mailbox) is None):
            continue

        try:
            _send_message(message)
        except Exception as exc:  # noqa: BLE001
            message.attempt_count += 1
            message.error = str(exc)
            if message.attempt_count >= SEND_MAX_ATTEMPTS:
                # Out of retries — this is the loud one: a reply we could not deliver.
                message.status = EmailMessage.Status.FAILED
                message.next_attempt_at = None
                notify(message.workspace, "error",
                       f"⛔ <b>Undelivered reply</b> to {message.to_addr} after "
                       f"{message.attempt_count} attempts:\n{message.subject}\n{exc}")
                SystemEvent.log("engine",
                                f"Send permanently failed to {message.to_addr} after "
                                f"{message.attempt_count} attempts: {exc}",
                                "error", workspace=message.workspace)
            else:
                # Transient — re-queue quietly, no Telegram spam for a retry.
                message.next_attempt_at = now + _retry_delay(message.attempt_count)
                SystemEvent.log("engine",
                                f"Send to {message.to_addr} failed (attempt "
                                f"{message.attempt_count}/{SEND_MAX_ATTEMPTS}), retry at "
                                f"{timezone.localtime(message.next_attempt_at):%H:%M}: {exc}",
                                "warning", workspace=message.workspace)
            message.save(update_fields=["status", "attempt_count", "next_attempt_at", "error"])
            continue

        message.status = EmailMessage.Status.SENT
        message.sent_at = timezone.now()
        message.attempt_count += 1
        message.error = ""
        message.next_attempt_at = None
        sent += 1
        notify(message.workspace, "sent", f"📤 <b>{message.mailbox.name}</b> sent reply:\n{message.subject}\nto {message.to_addr}")
        SystemEvent.log("engine", f"Sent reply to {message.to_addr}"
                        + (f" (after {message.attempt_count} attempts)" if message.attempt_count > 1 else ""),
                        "success", workspace=message.workspace)
        message.save(update_fields=["status", "sent_at", "attempt_count", "error", "next_attempt_at"])
    return sent


def _reply_fallback_route(workspace, mailbox=None):
    """A campaign route allowed to carry auto-replies for `mailbox`, or None.

    A fallback reply keeps the mailbox's own From address, so a route may only be
    used when it is authorised to send for that address's domain — otherwise the
    reply fails SPF/DKIM and lands in spam. `can_send_as` is the gate; without it a
    route verified for one domain would happily be used for another.

    Among eligible routes, the one with fewest sends today wins, so several
    fallbacks share the load rather than one absorbing everything.
    """
    from apps.campaigns.models import CampaignSender

    candidates = CampaignSender.objects.filter(
        workspace=workspace, is_active=True, use_for_replies=True
    ).exclude(kind=CampaignSender.Kind.MAILBOX)

    routes = []
    for route in candidates:
        if not route.has_quota():
            continue
        if mailbox is not None:
            allowed, _reason = route.can_send_as(mailbox.email_address)
            if not allowed:
                continue
        routes.append(route)
    if not routes:
        return None
    return min(routes, key=lambda r: r.sent_today / max(1, r.weight))


def _fallback_block_reason(workspace, mailbox) -> str:
    """Why no route can carry this mailbox's replies — for the log and the UI."""
    from apps.campaigns.models import CampaignSender

    candidates = list(
        CampaignSender.objects.filter(
            workspace=workspace, is_active=True, use_for_replies=True
        ).exclude(kind=CampaignSender.Kind.MAILBOX)
    )
    if not candidates:
        return "no fallback sending route is enabled"
    reasons = []
    for route in candidates:
        if not route.has_quota():
            reasons.append(f"{route.name}: out of quota today")
            continue
        allowed, reason = route.can_send_as(mailbox.email_address)
        if not allowed:
            reasons.append(f"{route.name}: {reason}")
    return "; ".join(reasons) or "no eligible route"


def _send_via_fallback(message: EmailMessage, route) -> None:
    """Send a reply through an external route, keeping the mailbox's own identity.

    The From address stays the mailbox's, so the thread still looks like it came
    from the person the sender wrote to — which also means the provider must be
    authorised for that domain (SPF/DKIM), or the reply lands in spam.
    """
    from apps.campaigns.models import Contact
    from apps.campaigns.sending import deliver

    from apps.campaigns.models import CampaignSender

    mailbox = message.mailbox
    headers = {"Auto-Submitted": "auto-replied"}
    if message.reply_to_message and message.reply_to_message.message_id:
        headers["In-Reply-To"] = message.reply_to_message.message_id
        headers["References"] = message.reply_to_message.message_id

    # Under ROUTE identity the mail goes out as the provider's own verified address
    # and the mailbox becomes Reply-To, so replies still come back to the right place.
    if route.reply_identity == CampaignSender.ReplyIdentity.ROUTE:
        from_override = ""
        headers["Reply-To"] = mailbox.email_address
    else:
        from_override = mailbox.email_address

    # deliver() addresses a Contact; an unsaved one carries the recipient without
    # adding this person to the campaign audience.
    allowed, reason = route.can_send_as(mailbox.email_address)
    if not allowed:
        # Selection already filtered on this; re-checked here so a route edited
        # mid-flight can never slip an unauthenticated reply out.
        raise RuntimeError(f"Route '{route.name}' cannot send as {mailbox.email_address}: {reason}")

    recipient = Contact(email=message.to_addr, unsubscribe_token=f"reply-{message.pk}")
    deliver(
        route, recipient, message.subject, message.body, message.is_html,
        list(message.attachments.all()),
        from_override=from_override,
        extra_headers=headers,
    )
    route.record_send()
    SystemEvent.log(
        "engine",
        f"Mailbox {mailbox.name} is at its daily cap; reply to {message.to_addr} sent via {route.name}",
        workspace=message.workspace,
    )


def _send_message(message: EmailMessage):
    mailbox = message.mailbox
    # Mailbox out of daily quota? Borrow a fallback route rather than pushing the
    # account past a limit that gets it throttled or suspended.
    if not mailbox.has_send_quota():
        route = _reply_fallback_route(message.workspace, mailbox)
        if route is None:
            raise RuntimeError(
                f"Mailbox '{mailbox.name}' has hit its daily send limit "
                f"({mailbox.daily_send_limit}) and no route can send as "
                f"{mailbox.email_address} — {_fallback_block_reason(message.workspace, mailbox)}."
            )
        _send_via_fallback(message, route)
        return

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
    # Only a delivered message counts against the cap; a failed attempt will retry.
    mailbox.record_send()


def run_once(workspace=None, force=False) -> dict:
    """One full engine tick: poll due mailboxes, send due replies, run campaigns.

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
    # Campaigns ride the same tick as auto-replies, so bulk sending needs no second
    # process. Imported here rather than at module scope: apps.campaigns imports the
    # engine for its renderer, and a top-level import would close that circle.
    from apps.campaigns.runner import run_campaigns

    stats["campaign_sent"] = run_campaigns(workspace=workspace)
    return stats
