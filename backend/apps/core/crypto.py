"""Symmetric encryption for binary blobs stored at rest.

Shares the same Fernet key and dev fallback as mailbox credential encryption
(see apps.mailboxes.crypto) so there is a single secret to manage:
MAIL_ENCRYPTION_KEY. Mailboxes keep their string-oriented wrappers; this module
handles raw bytes (uploaded files, rendered pages) for the protected_content app.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        # Deterministic dev fallback derived from SECRET_KEY, matching
        # apps.mailboxes.crypto so both read/write the same ciphertext in dev.
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes. Returns the Fernet token as bytes."""
    if data is None:
        return b""
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    """Decrypt a token produced by encrypt_bytes. Returns b'' if unreadable."""
    if not token:
        return b""
    if isinstance(token, str):
        token = token.encode()
    try:
        return _fernet().decrypt(token)
    except InvalidToken:
        return b""
