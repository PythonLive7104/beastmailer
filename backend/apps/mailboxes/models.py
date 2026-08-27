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

    # Outgoing volume cap. Consumer Gmail cuts off near 500/day and Workspace near
    # 2000; exceeding it gets the account throttled or suspended, so the engine
    # counts sends and diverts to a fallback route once the cap is reached.
    # 0 = no cap, which is the pre-existing behaviour for mailboxes created before
    # this field existed.
    daily_send_limit = models.PositiveIntegerField(
        default=0, help_text="Max emails per day from this account. 0 = no limit."
    )
    sent_today = models.PositiveIntegerField(default=0)
    send_day_started = models.DateField(null=True, blank=True)

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

    def roll_send_counter(self, now=None):
        """Zero the daily counter when the date has moved on."""
        from django.utils import timezone

        today = timezone.localdate(now or timezone.now())
        if self.send_day_started != today:
            self.send_day_started = today
            self.sent_today = 0
            self.save(update_fields=["send_day_started", "sent_today"])

    def has_send_quota(self, now=None) -> bool:
        self.roll_send_counter(now)
        return not self.daily_send_limit or self.sent_today < self.daily_send_limit

    def record_send(self):
        self.sent_today += 1
        self.save(update_fields=["sent_today"])

    def remaining_sends_today(self):
        """Sends left today, or None when the mailbox is uncapped."""
        if not self.daily_send_limit:
            return None
        self.roll_send_counter()
        return max(0, self.daily_send_limit - self.sent_today)
