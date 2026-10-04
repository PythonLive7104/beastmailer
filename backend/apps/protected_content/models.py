from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from apps.core.crypto import decrypt_bytes, encrypt_bytes


class ProtectedDocument(models.Model):
    """A page or file served only through a server-side gate.

    The payload is stored encrypted at rest in `ciphertext` (never under
    MEDIA_ROOT), so there is no direct URL to the raw file. Access is enforced
    on the server — passcode, expiry, view cap, referrer — and audited; the
    browser never receives the content until a request passes every check.
    """

    KIND_PAGE = "page"
    KIND_FILE = "file"
    KIND_CHOICES = [(KIND_PAGE, "Inline page"), (KIND_FILE, "File download")]

    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="protected_documents"
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True, help_text="Public URL /g/<slug>/")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_PAGE)

    # Encrypted payload. Bytea/BLOB; the plaintext is never persisted.
    ciphertext = models.BinaryField(blank=True)
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0, help_text="Plaintext size in bytes")

    # --- Server-enforced access controls ---
    passcode_hash = models.CharField(max_length=256, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    max_views = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited")
    view_count = models.PositiveIntegerField(default=0)
    allowed_referrers = models.CharField(
        max_length=500, blank=True, default="", help_text="Comma-separated; blank = no check"
    )
    is_active = models.BooleanField(default=True)

    # --- Cosmetic browser deterrents (weak; labelled as such in the UI) ---
    disable_right_click = models.BooleanField(default=False)
    disable_copy = models.BooleanField(default=False)
    disable_print = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    # --- Payload helpers: callers deal in plaintext, storage stays encrypted ---
    def set_payload(self, data: bytes):
        self.size = len(data or b"")
        self.ciphertext = encrypt_bytes(data or b"")

    def get_payload(self) -> bytes:
        return decrypt_bytes(bytes(self.ciphertext))

    # --- Passcode helpers ---
    def set_passcode(self, raw: str):
        self.passcode_hash = make_password(raw) if raw else ""

    def check_passcode(self, raw: str) -> bool:
        if not self.passcode_hash:
            return True
        return check_password(raw or "", self.passcode_hash)

    @property
    def requires_passcode(self) -> bool:
        return bool(self.passcode_hash)


class ProtectedAsset(models.Model):
    """An image/asset belonging to a protected page, served only through the gate.

    Stored encrypted like the page itself. A protected page references it by its
    gated URL (/g/<slug>/asset/<id>/), so there is no direct /media/ path to
    hotlink or guess — this is the real version of Protware's image protection.
    """

    document = models.ForeignKey(
        ProtectedDocument, on_delete=models.CASCADE, related_name="assets"
    )
    name = models.CharField(max_length=200)
    ciphertext = models.BinaryField(blank=True)
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def set_payload(self, data: bytes):
        self.size = len(data or b"")
        self.ciphertext = encrypt_bytes(data or b"")

    def get_payload(self) -> bytes:
        return decrypt_bytes(bytes(self.ciphertext))


class ProtectedAccessLog(models.Model):
    """One row per access attempt against a ProtectedDocument."""

    OUTCOME_GRANTED = "granted"
    OUTCOME_DENIED_PASSCODE = "denied_passcode"
    OUTCOME_EXPIRED = "expired"
    OUTCOME_OVER_LIMIT = "over_limit"
    OUTCOME_DENIED_REFERRER = "denied_referrer"
    OUTCOME_INACTIVE = "inactive"
    OUTCOME_CHOICES = [
        (OUTCOME_GRANTED, "Granted"),
        (OUTCOME_DENIED_PASSCODE, "Denied — passcode"),
        (OUTCOME_EXPIRED, "Expired"),
        (OUTCOME_OVER_LIMIT, "Over view limit"),
        (OUTCOME_DENIED_REFERRER, "Denied — referrer"),
        (OUTCOME_INACTIVE, "Inactive"),
    ]

    document = models.ForeignKey(
        ProtectedDocument, on_delete=models.CASCADE, related_name="access_logs"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    referrer = models.CharField(max_length=500, blank=True, default="")
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.document_id} {self.outcome} @ {self.created_at:%Y-%m-%d %H:%M}"
