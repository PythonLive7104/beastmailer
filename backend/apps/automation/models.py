from django.db import models


class Config(models.Model):
    """Per-workspace automation settings (one row per workspace)."""

    workspace = models.OneToOneField("workspaces.Workspace", on_delete=models.CASCADE, related_name="config")
    auto_reply_enabled = models.BooleanField(default=True)
    reply_delay_minutes = models.PositiveIntegerField(
        default=10, help_text="Wait this long after receiving before sending an auto-reply"
    )
    poll_interval_seconds = models.PositiveIntegerField(
        default=10, help_text="How often the engine checks mailboxes for new mail"
    )
    signature = models.TextField(blank=True, default="", help_text="Appended to every auto-reply")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuration"
        verbose_name_plural = "configuration"

    def __str__(self):
        return f"Config for {self.workspace}"

    @classmethod
    def load(cls, workspace) -> "Config":
        obj, _ = cls.objects.get_or_create(workspace=workspace)
        return obj
