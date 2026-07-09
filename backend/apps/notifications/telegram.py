"""Telegram Bot API helper — uses urllib so there are no extra dependencies."""
import json
import urllib.error
import urllib.parse
import urllib.request

from .models import TelegramConfig


def send_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Low-level send. Returns (ok, error_message)."""
    if not token or not chat_id:
        return False, "Bot token and chat ID are required."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as resp:
            payload = json.loads(resp.read().decode())
            if payload.get("ok"):
                return True, ""
            return False, payload.get("description", "Unknown Telegram error")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
            return False, body.get("description", str(exc))
        except Exception:  # noqa: BLE001
            return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def notify(workspace, event: str, text: str) -> None:
    """Fire a notification to `workspace`'s Telegram if enabled and opted in.

    `event` is one of: sent, received, error. Failures are swallowed so a
    notification problem never breaks the mail engine.
    """
    try:
        if workspace is None:
            return
        cfg = TelegramConfig.load(workspace)
        if not cfg.enabled:
            return
        opt = {"sent": cfg.notify_on_sent, "received": cfg.notify_on_received,
               "error": cfg.notify_on_error}.get(event, False)
        if not opt:
            return
        send_message(cfg.bot_token, cfg.chat_id, text)
    except Exception:  # noqa: BLE001
        pass
