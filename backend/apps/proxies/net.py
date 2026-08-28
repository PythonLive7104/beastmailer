"""Proxy-aware socket helpers for SMTP sending and connectivity tests.

PySocks is imported lazily so the rest of the app still runs when it isn't
installed — it's only needed once a mailbox actually routes through a proxy.
"""
import smtplib
import ssl
import time


def _socks():
    try:
        import socks  # PySocks
    except ImportError as exc:  # pragma: no cover - surfaced to the UI/logs
        raise RuntimeError(
            "Proxy support requires the 'PySocks' package. Install it: pip install PySocks"
        ) from exc
    return socks


def _proxy_type(socks, kind):
    return {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }.get(kind, socks.SOCKS5)


def proxy_socket(proxy, dest_host, dest_port, timeout=30):
    """Open a raw TCP socket to (dest_host, dest_port) through `proxy`."""
    socks = _socks()
    return socks.create_connection(
        (dest_host, dest_port),
        timeout=timeout,
        proxy_type=_proxy_type(socks, proxy.kind),
        proxy_addr=proxy.host,
        proxy_port=proxy.port,
        proxy_username=proxy.username or None,
        proxy_password=proxy.password or None,
    )


class ProxySMTP(smtplib.SMTP):
    """smtplib.SMTP that dials the server through a proxy when one is given."""

    def __init__(self, host="", port=0, *, proxy=None, timeout=30, **kw):
        self._proxy = proxy
        super().__init__(host, port, timeout=timeout, **kw)

    def _get_socket(self, host, port, timeout):
        if self._proxy is not None:
            return proxy_socket(self._proxy, host, port, timeout)
        return super()._get_socket(host, port, timeout)


class ProxySMTP_SSL(smtplib.SMTP_SSL):
    """SMTP_SSL (implicit TLS, port 465) that dials through a proxy when given."""

    def __init__(self, host="", port=0, *, proxy=None, timeout=30, context=None, **kw):
        self._proxy = proxy
        super().__init__(host, port, timeout=timeout, context=context, **kw)

    def _get_socket(self, host, port, timeout):
        if self._proxy is not None:
            sock = proxy_socket(self._proxy, host, port, timeout)
            return self.context.wrap_socket(sock, server_hostname=self._host)
        return super()._get_socket(host, port, timeout)


# Port 465 is "implicit TLS": the server begins the TLS handshake the moment the
# socket opens. Port 587 (and 25) are "explicit TLS": you connect in the clear and
# upgrade with STARTTLS. Using the wrong one does not fail cleanly — it hangs until
# the timeout, because each side is waiting for the other to speak first.
IMPLICIT_TLS_PORTS = {465}


def smtp_connect(host, port, username="", password="", use_tls=True, proxy=None, timeout=30):
    """Open an authenticated SMTP connection, choosing the right TLS mechanism.

    The port decides the mechanism, not the caller's checkbox. Trusting the flag is
    what broke every provider that uses 465 (Titan, Zoho, Fastmail, most cPanel
    hosts): the form defaults the flag to on, so a 465 mailbox tried to STARTTLS
    against a socket already expecting a TLS handshake and simply hung.
    """
    port = int(port or 587)
    if port in IMPLICIT_TLS_PORTS:
        smtp = ProxySMTP_SSL(host, port, proxy=proxy, timeout=timeout)
    else:
        smtp = ProxySMTP(host, port, proxy=proxy, timeout=timeout)
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            # Upgrade whenever the server offers it, even if the flag was off:
            # that only ever turns a plaintext login into an encrypted one.
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        elif use_tls:
            # Asked for encryption and the server cannot provide it. Better to stop
            # than to send the password in the clear.
            smtp.quit()
            raise smtplib.SMTPException(
                f"{host}:{port} does not offer STARTTLS. If this provider uses SSL, "
                f"set the port to 465 instead."
            )
    if username:
        smtp.login(username, password)
    return smtp


def open_smtp(mailbox, proxy=None, timeout=30):
    """Open an authenticated SMTP connection for a Mailbox."""
    return smtp_connect(
        mailbox.smtp_host, mailbox.smtp_port, mailbox.username, mailbox.password,
        use_tls=mailbox.smtp_use_tls, proxy=proxy, timeout=timeout,
    )


def test_proxy(proxy, timeout=15) -> dict:
    """Verify a proxy works end-to-end and report the exit IP it presents."""
    start = time.time()
    try:
        sock = proxy_socket(proxy, "api.ipify.org", 443, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report any failure to the UI
        return {"ok": False, "error": str(exc)}
    try:
        ctx = ssl.create_default_context()
        ssock = ctx.wrap_socket(sock, server_hostname="api.ipify.org")
        ssock.sendall(
            b"GET /?format=text HTTP/1.0\r\nHost: api.ipify.org\r\n"
            b"User-Agent: beastmailer\r\n\r\n"
        )
        raw = b""
        while len(raw) < 65536:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            raw += chunk
        try:
            ssock.close()
        except Exception:  # noqa: BLE001
            pass
        text = raw.split(b"\r\n\r\n", 1)[-1].decode("utf-8", "replace").strip()
        exit_ip = text.split()[-1] if text else ""
        return {"ok": True, "exit_ip": exit_ip[:64], "latency_ms": int((time.time() - start) * 1000)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
