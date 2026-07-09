from django.db import models


class Link(models.Model):
    """A named, reusable link that can be dropped into reply templates.

    Templates can embed either the raw `url` or the tracked redirect
    (`/r/<slug>/`), which counts clicks before forwarding. The slug stays
    globally unique so the public tracking URL is unambiguous across users.
    """

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="links")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True, help_text="Used in the tracking URL /r/<slug>/")
    url = models.URLField(max_length=1000)
    description = models.CharField(max_length=255, blank=True, default="")
    clicks = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
