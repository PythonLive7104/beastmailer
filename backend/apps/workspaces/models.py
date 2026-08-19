import secrets

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    """A shared container that owns all mail data. Users join via Membership."""

    name = models.CharField(max_length=120)
    is_personal = models.BooleanField(default=False, help_text="Auto-created solo workspace")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Links a user to a workspace with a role."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("workspace", "user")]
        ordering = ["role", "user__username"]

    def __str__(self):
        return f"{self.user} @ {self.workspace} ({self.role})"

    @property
    def can_manage(self) -> bool:
        return self.role in (self.Role.OWNER, self.Role.ADMIN)


class UserProfile(models.Model):
    """Per-user settings, notably which workspace they're currently viewing."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    current_workspace = models.ForeignKey(
        Workspace, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Set once the user finishes (or skips) the step-by-step setup guide, so the
    # walkthrough auto-opens on first login only and can be replayed from Settings.
    onboarding_completed = models.BooleanField(default=False)


def _new_code() -> str:
    return secrets.token_urlsafe(24)


class Invitation(models.Model):
    """An invite to join a workspace. Existing users are added immediately;
    otherwise a code is shared and redeemed after signup."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(blank=True, default="")
    role = models.CharField(max_length=10, choices=Membership.Role.choices, default=Membership.Role.MEMBER)
    code = models.CharField(max_length=64, unique=True, default=_new_code)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite to {self.workspace} ({self.code})"
