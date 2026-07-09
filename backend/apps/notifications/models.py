from django.db import models

from apps.mailboxes.crypto import decrypt, encrypt


class TelegramConfig(models.Model):
    """Per-workspace Telegram bot config for push notifications."""

    workspace = models.OneToOneField("workspaces.Workspace", on_delete=models.CASCADE, related_name="telegram_config")
    enabled = models.BooleanField(default=False)
    bot_token_encrypted = models.TextField(blank=True, default="")
    chat_id = models.CharField(max_length=64, blank=True, default="")

    notify_on_sent = models.BooleanField(default=True)
    notify_on_received = models.BooleanField(default=False)
    notify_on_error = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram configuration"
        verbose_name_plural = "Telegram configuration"

    @classmethod
    def load(cls, workspace) -> "TelegramConfig":
        obj, _ = cls.objects.get_or_create(workspace=workspace)
        return obj

    @property
    def bot_token(self) -> str:
        return decrypt(self.bot_token_encrypted)

    @bot_token.setter
    def bot_token(self, value: str):
        self.bot_token_encrypted = encrypt(value or "")
