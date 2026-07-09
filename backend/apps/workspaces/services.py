"""Helpers for resolving the active workspace and managing membership."""
from .models import Membership, UserProfile, Workspace


def ensure_personal_workspace(user) -> Workspace:
    """Guarantee the user has at least one workspace and a profile pointing at one.

    Called on registration and lazily whenever we need an active workspace.
    """
    profile, _ = UserProfile.objects.get_or_create(user=user)

    membership = Membership.objects.filter(user=user).select_related("workspace").first()
    if membership is None:
        ws = Workspace.objects.create(name=f"{user.username}'s workspace", is_personal=True)
        Membership.objects.create(workspace=ws, user=user, role=Membership.Role.OWNER)
    else:
        ws = membership.workspace

    if profile.current_workspace_id is None or not Membership.objects.filter(
        user=user, workspace=profile.current_workspace_id
    ).exists():
        profile.current_workspace = ws
        profile.save(update_fields=["current_workspace"])
    return profile.current_workspace


def active_workspace(user) -> Workspace:
    """The workspace the user is currently operating in (self-healing)."""
    profile = getattr(user, "profile", None)
    if profile and profile.current_workspace_id:
        if Membership.objects.filter(user=user, workspace=profile.current_workspace_id).exists():
            return profile.current_workspace
    return ensure_personal_workspace(user)


def user_role(user, workspace) -> str | None:
    m = Membership.objects.filter(user=user, workspace=workspace).first()
    return m.role if m else None


def can_manage(user, workspace) -> bool:
    return user_role(user, workspace) in (Membership.Role.OWNER, Membership.Role.ADMIN)
