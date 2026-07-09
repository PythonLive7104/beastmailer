"""Symmetric encryption for mailbox credentials stored at rest.

Uses Fernet (AES-128-CBC + HMAC). The key comes from MAIL_ENCRYPTION_KEY in the
environment. In dev, if unset, a key is derived deterministically from
SECRET_KEY so the app runs out of the box — but you MUST set a real key in
production, otherwise rotating SECRET_KEY makes stored passwords unreadable.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        # Deterministic dev fallback derived from SECRET_KEY.
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
