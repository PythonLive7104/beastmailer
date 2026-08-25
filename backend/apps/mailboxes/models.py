from django.core.validators import MinValueValidator
from django.db import models

from .crypto import decrypt, encrypt


class Mailbox(models.Model):
    """An email account the app connects to via IMAP (read) and SMTP (send)."""

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="mailboxes")
    name = models.CharField(max_length=120, help_text="Friendly label, e.g. 'Sales inbox'")
    email_address = models.EmailField()

    # IMAP (incoming)
    imap_host = models.CharField(max_length=200)
    imap_port = models.PositiveIntegerField(default=993)
    imap_use_ssl = models.BooleanField(default=True)

    # SMTP (outgoing)
    smtp_host = models.CharField(max_length=200)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)

    # Auth — username often equals the email address. Password is encrypted.
    username = models.CharField(max_length=200)
    password_encrypted = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    # Client mail routinely lands in Spam, so by default we poll the account's junk
    # folder alongside INBOX. Its name varies by provider ("[Gmail]/Spam", "Bulk
    # Mail", "Junk"), so the engine finds it by the RFC 6154 \Junk flag, not by name.
    scan_spam = models.BooleanField(
        default=True,
        help_text="Also scan this account's Spam/Junk folder for incoming mail.",
    )
    extra_folders = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Extra IMAP folders to scan, comma-separated (e.g. 'Promotions, Archive').",
    )
    # When on, outgoing SMTP for this mailbox is routed through a random proxy
    # from the workspace pool (see apps.proxies). Off = direct connection.
    use_proxy = models.BooleanField(default=False)
    # Per-account timing. Blank falls back to the workspace Config, so existing
    # mailboxes keep behaving exactly as before until someone sets an override.
    poll_interval_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(10)],
        help_text="How often to check this account. Blank = workspace default.",
    )
    reply_delay_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Wait this long before auto-replying from this account. Blank = workspace default.",
    )

    last_polled_at = models.DateTimeField(null=True, blank=True)
    # Per-folder read cursor: {"INBOX": {"uid": 42, "uidvalidity": 7}, ...}. IMAP UIDs
    # are only unique within one folder, so every folder needs its own high-water mark.
    folder_cursors = models.JSONField(default=dict, blank=True)
    # The INBOX cursor, mirrored here for the UI and for mailboxes created before
    # folder_cursors existed (which the engine seeds from on the first poll).
    last_seen_uid = models.PositiveBigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "mailboxes"

    def __str__(self):
        return f"{self.name} <{self.email_address}>"

    @property
    def extra_folder_list(self) -> list[str]:
        return [f.strip() for f in (self.extra_folders or "").split(",") if f.strip()]

    # Password is set/read through this property so callers never touch ciphertext.
    @property
    def password(self) -> str:
        return decrypt(self.password_encrypted)

    @password.setter
    def password(self, value: str):
        self.password_encrypted = encrypt(value or "")
