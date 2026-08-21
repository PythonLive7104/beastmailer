"""Subscription checks shared by the engine, the API, and the admin.

Access is per user. The engine sends mail for a *workspace*, so it gates on that
workspace's owner: if the owner's access window has lapsed, the workspace's
mailboxes stop sending (polling and configuration are unaffected — the paywall is
"sending only").
"""
from django.utils import timezone

from apps.workspaces.models import Membership

from .models import BillingSettings, active_period_end


def billing_enabled() -> bool:
    return BillingSettings.load().is_enabled


def user_is_subscribed(user) -> bool:
    """True if this user may use paid features right now.

    Staff/superusers are always exempt, and when billing is switched off everyone
    passes — so the paywall can be turned on later without stranding anyone.
    """
    if user is None:
        return False
    if user.is_staff or user.is_superuser:
        return True
    if not billing_enabled():
        return True
    end = active_period_end(user)
    return bool(end and end > timezone.now())


def workspace_owner(workspace):
    m = (
        Membership.objects.filter(workspace=workspace, role=Membership.Role.OWNER)
        .select_related("user")
        .first()
    )
    return m.user if m else None


def workspace_can_send(workspace) -> bool:
    """Whether the engine may send auto-replies for this workspace."""
    if not billing_enabled():
        return True
    owner = workspace_owner(workspace)
    return user_is_subscribed(owner) if owner else False
