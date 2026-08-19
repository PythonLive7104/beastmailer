"""Test a saved proxy against a mailbox's real SMTP port.

The Proxies page's built-in test only dials api.ipify.org:443, which every proxy
allows. Mail ports are the ones providers block, so that test can pass while every
send still fails. This command walks the same path the engine uses, one stage at a
time, so a failure points at the stage that broke.

Usage:
    python manage.py test_proxy_smtp --list
    python manage.py test_proxy_smtp --proxy 3 --mailbox 1
    python manage.py test_proxy_smtp --proxy "US-1" --mailbox "Sales inbox"
    python manage.py test_proxy_smtp --proxy 3 --host smtp.gmail.com --port 587
    python manage.py test_proxy_smtp --proxy 3 --mailbox 1 --send-to you@example.com
"""
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage

from django.core.management.base import BaseCommand, CommandError

from apps.mailboxes.models import Mailbox
from apps.proxies.models import Proxy
from apps.proxies.net import open_smtp, proxy_socket, test_proxy


def _resolve(model, ref, name_field, label):
    """Look a record up by primary key, or by a case-insensitive name match."""
    if ref.isdigit():
        try:
            return model.objects.get(pk=int(ref))
        except model.DoesNotExist:
            raise CommandError(f"No {label} with id {ref}. Try --list.")
    matches = list(model.objects.filter(**{f"{name_field}__icontains": ref}))
    if not matches:
        raise CommandError(f"No {label} matching {ref!r}. Try --list.")
    if len(matches) > 1:
        names = ", ".join(f"{m.pk}:{getattr(m, name_field)}" for m in matches)
        raise CommandError(f"{ref!r} matches several {label}s ({names}). Use the id.")
    return matches[0]


class Command(BaseCommand):
    help = "Check that a proxy can carry SMTP to a mailbox's real mail port."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="List saved proxies and mailboxes, then exit.")
        parser.add_argument("--proxy", help="Proxy id or label.")
        parser.add_argument("--mailbox", help="Mailbox id or name — supplies host, port and login.")
        parser.add_argument("--host", help="SMTP host, when testing without a mailbox.")
        parser.add_argument("--port", type=int, help="SMTP port, when testing without a mailbox (default 587).")
        parser.add_argument("--send-to", help="Deliver a real test message to this address.")
        parser.add_argument("--timeout", type=int, default=30, help="Per-stage timeout in seconds (default 30).")

    def handle(self, *args, **opts):
        if opts["list"]:
            return self._list()
        if not opts["proxy"]:
            raise CommandError("--proxy is required. Run with --list to see what's saved.")

        proxy = _resolve(Proxy, opts["proxy"], "label", "proxy")
        mailbox = _resolve(Mailbox, opts["mailbox"], "name", "mailbox") if opts["mailbox"] else None

        # A mailbox supplies the real destination; --host/--port covers testing a
        # proxy before any mailbox exists. Without either there is nothing to dial.
        host = opts["host"] or (mailbox.smtp_host if mailbox else None)
        port = opts["port"] or (mailbox.smtp_port if mailbox else 587)
        if not host:
            raise CommandError("Give me a destination: --mailbox, or --host with --port.")
        if opts["send_to"] and not mailbox:
            raise CommandError("--send-to needs --mailbox: the message is sent as that account.")

        self.stdout.write(f"proxy    {proxy.label}  ({proxy.kind} {proxy.host}:{proxy.port})")
        self.stdout.write(f"target   {host}:{port}" + (f"  via {mailbox.name}" if mailbox else ""))
        self.stdout.write("")

        # A failing stage exits non-zero so this is usable as a CI/pre-delivery check.
        if not self._stage_exit_ip(proxy, opts["timeout"]):
            raise SystemExit(1)
        if not self._stage_mail_port(proxy, host, port, opts["timeout"]):
            raise SystemExit(1)
        if mailbox is None:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Proxy reaches the mail port. Pass --mailbox to test login."))
            return
        if not self._stage_login(proxy, mailbox, opts["timeout"], opts["send_to"]):
            raise SystemExit(1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("All stages passed — this proxy can carry mail for this mailbox."))

    # --- stages -----------------------------------------------------------
    # Each returns True to continue. They run in order of increasing depth so the
    # first failure names the layer at fault instead of one opaque timeout.

    def _stage_exit_ip(self, proxy, timeout):
        """Is the proxy alive at all, and which IP does the world see?"""
        result = test_proxy(proxy, timeout=timeout)
        if not result["ok"]:
            self._fail("1/3  proxy reachable", result["error"])
            self.stdout.write("      The proxy itself is down or the credentials are wrong.")
            self.stdout.write("      Nothing below this can work until it answers on port 443.")
            return False
        self._ok("1/3  proxy reachable", f"exit IP {result['exit_ip']}  ({result['latency_ms']} ms)")
        return True

    def _stage_mail_port(self, proxy, host, port, timeout):
        """The stage the built-in test skips: does the proxy allow the mail port?"""
        start = time.time()
        try:
            sock = proxy_socket(proxy, host, port, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - any failure is a usable answer here
            self._fail(f"2/3  connect to {host}:{port}", str(exc))
            self.stdout.write(f"      Stage 1 passed, so the proxy works — it just refused port {port}.")
            self.stdout.write("      Providers block mail ports to deter spam. Ask yours to open")
            self.stdout.write(f"      {port} for this proxy, or use one sold for mail traffic.")
            return False
        try:
            sock.close()
        except Exception:  # noqa: BLE001 - already have the answer we came for
            pass
        self._ok(f"2/3  connect to {host}:{port}", f"open  ({int((time.time() - start) * 1000)} ms)")
        return True

    def _stage_login(self, proxy, mailbox, timeout, send_to):
        """The engine's own send path — TLS negotiation and SMTP AUTH included."""
        start = time.time()
        try:
            smtp = open_smtp(mailbox, proxy=proxy, timeout=timeout)
        except smtplib.SMTPAuthenticationError as exc:
            self._fail("3/3  SMTP login", str(exc))
            self.stdout.write("      The tunnel is fine; the mailbox credentials were rejected.")
            self.stdout.write("      Gmail and Outlook need an app password here, not the account password.")
            return False
        except (ssl.SSLError, smtplib.SMTPException, socket.timeout, OSError) as exc:
            self._fail("3/3  SMTP login", str(exc))
            self.stdout.write(f"      Port {mailbox.smtp_port} accepted the connection but the SMTP")
            self.stdout.write("      conversation failed. Check smtp_use_tls against the port:")
            self.stdout.write("      587 wants STARTTLS on, 465 wants it off.")
            return False
        self._ok("3/3  SMTP login", f"authenticated as {mailbox.username}  ({int((time.time() - start) * 1000)} ms)")

        try:
            if send_to:
                self._send(smtp, mailbox, proxy, send_to)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001 - the test already succeeded
                pass
        return True

    def _send(self, smtp, mailbox, proxy, send_to):
        """Deliver a real message — the only proof the whole chain works."""
        msg = EmailMessage()
        msg["Subject"] = "BeastMailer proxy test"
        msg["From"] = mailbox.email_address
        msg["To"] = send_to
        msg.set_content(
            f"Sent through proxy {proxy.label} ({proxy.kind} {proxy.host}:{proxy.port})\n"
            f"via {mailbox.smtp_host}:{mailbox.smtp_port} as {mailbox.email_address}.\n\n"
            "Check this message's Received headers to confirm the proxy IP is the one "
            "the receiving server recorded."
        )
        try:
            smtp.send_message(msg)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            self._fail("send  test message", str(exc))
            return
        self._ok("send  test message", f"delivered to {send_to}")

    # --- output -----------------------------------------------------------

    def _ok(self, label, detail):
        self.stdout.write(f"{self.style.SUCCESS('ok')}    {label}  {detail}")

    def _fail(self, label, detail):
        self.stdout.write(f"{self.style.ERROR('FAIL')}  {label}")
        self.stdout.write(f"      {detail}")

    def _list(self):
        proxies = Proxy.objects.all()
        self.stdout.write(self.style.MIGRATE_HEADING("Proxies"))
        if not proxies:
            self.stdout.write("  (none saved)")
        for p in proxies:
            state = "active" if p.is_active else "inactive"
            self.stdout.write(f"  {p.pk:>3}  {p.label}  —  {p.kind} {p.host}:{p.port}  [{state}]")

        boxes = Mailbox.objects.all()
        self.stdout.write(self.style.MIGRATE_HEADING("Mailboxes"))
        if not boxes:
            self.stdout.write("  (none saved)")
        for m in boxes:
            tls = "STARTTLS" if m.smtp_use_tls else "no STARTTLS"
            self.stdout.write(f"  {m.pk:>3}  {m.name}  —  {m.smtp_host}:{m.smtp_port} ({tls})")
