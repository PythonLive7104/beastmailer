from django.db import models


class SystemEvent(models.Model):
    """Lightweight audit log of engine and admin actions shown on the Security page."""

    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    # Nullable: some events (e.g. a failed login for an unknown user) have no workspace.
    workspace = models.ForeignKey(
        "workspaces.Workspace", null=True, blank=True, on_delete=models.CASCADE, related_name="events"
    )
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    category = models.CharField(max_length=40, help_text="e.g. engine, mailbox, auth")
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.level}] {self.message}"

    @classmethod
    def log(cls, category: str, message: str, level: str = "info", workspace=None):
        try:
            cls.objects.create(category=category, message=message[:500], level=level, workspace=workspace)
        except Exception:  # noqa: BLE001 - auditing must never break the caller
            pass
