import random

from django.db import models
from django.utils import timezone

from apps.mailboxes.crypto import decrypt, encrypt


class Proxy(models.Model):
    """A proxy the engine can route outgoing SMTP connections through.

    A workspace keeps a pool of these; when a mailbox has `use_proxy` on, each
    send picks a random active proxy (with failover) so the connecting IP varies.
    """

    class Kind(models.TextChoices):
        SOCKS5 = "socks5", "SOCKS5"
        SOCKS4 = "socks4", "SOCKS4"
        HTTP = "http", "HTTP CONNECT"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="proxies")
    label = models.CharField(max_length=120, help_text="Friendly name, e.g. 'Residential US-1'")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SOCKS5)
    host = models.CharField(max_length=200)
    port = models.PositiveIntegerField()
    username = models.CharField(max_length=200, blank=True, default="")
    password_encrypted = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    failure_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]
        verbose_name_plural = "proxies"

    def __str__(self):
        return f"{self.label} ({self.kind} {self.host}:{self.port})"

    # Credentials are set/read through this property so callers never touch ciphertext.
    @property
    def password(self) -> str:
        return decrypt(self.password_encrypted)

    @password.setter
    def password(self, value: str):
        self.password_encrypted = encrypt(value or "")

    def mark_ok(self):
        self.last_used_at = timezone.now()
        self.last_error = ""
        self.failure_count = 0
        self.save(update_fields=["last_used_at", "last_error", "failure_count"])

    def mark_failed(self, error: str):
        self.last_used_at = timezone.now()
        self.last_error = error[:500]
        self.failure_count = models.F("failure_count") + 1
        self.save(update_fields=["last_used_at", "last_error", "failure_count"])

    @classmethod
    def pick_random(cls, workspace, exclude_ids=()):
        """Return a random active proxy for the workspace, or None if the pool is empty."""
        ids = list(
            cls.objects.filter(workspace=workspace, is_active=True)
            .exclude(id__in=exclude_ids)
            .values_list("id", flat=True)
        )
        if not ids:
            return None
        return cls.objects.get(id=random.choice(ids))
