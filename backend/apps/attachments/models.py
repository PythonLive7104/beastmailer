from django.db import models


class Attachment(models.Model):
    """A saved file (brochure, price list…) that rules can attach to replies."""

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=160)
    file = models.FileField(upload_to="attachments/")
    description = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.file and not self.size:
            self.size = self.file.size
        super().save(*args, **kwargs)
