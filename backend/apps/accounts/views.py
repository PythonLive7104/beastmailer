from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.security.models import SystemEvent
from apps.workspaces.services import active_workspace, ensure_personal_workspace

User = get_user_model()


def _user_dict(user):
    ws = active_workspace(user)
    profile = getattr(user, "profile", None)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "onboarding_completed": bool(profile and profile.onboarding_completed),
        "workspace": {"id": ws.id, "name": ws.name} if ws else None,
    }


def _user_payload(user, token):
    return {"token": token.key, "user": _user_dict(user)}


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    username = (request.data.get("username") or "").strip()
    email = (request.data.get("email") or "").strip()
    password = request.data.get("password") or ""

    if not username or not password:
        return Response({"error": "Username and password are required."}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"error": "That username is already taken."}, status=400)
    try:
        validate_password(password)
    except ValidationError as exc:
        return Response({"error": " ".join(exc.messages)}, status=400)

    user = User.objects.create_user(username=username, email=email, password=password)
    ensure_personal_workspace(user)
    token, _ = Token.objects.get_or_create(user=user)
    SystemEvent.log("auth", f"New account registered: {username}", "success",
                    workspace=active_workspace(user))
    return Response(_user_payload(user, token), status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    identifier = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    # Match the username case-insensitively (and allow logging in by email), then
    # authenticate with the stored exact username. Registration only enforces
    # case-insensitive uniqueness, so login must be case-insensitive too.
    account = User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)
    ).first()
    user = authenticate(username=account.username, password=password) if account else None

    if user is None:
        SystemEvent.log("auth", f"Failed login for '{identifier}'", "warning")
        return Response({"error": "Invalid username or password."}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    return Response(_user_payload(user, token))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(_user_dict(request.user))


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update the logged-in user's own personal data: username, email, name."""
    user = request.user
    data = request.data

    if "username" in data:
        username = (data.get("username") or "").strip()
        if not username:
            return Response({"error": "Username cannot be empty."}, status=400)
        if User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            return Response({"error": "That username is already taken."}, status=400)
        user.username = username

    if "email" in data:
        user.email = (data.get("email") or "").strip()
    if "first_name" in data:
        user.first_name = (data.get("first_name") or "").strip()
    if "last_name" in data:
        user.last_name = (data.get("last_name") or "").strip()

    user.save()
    SystemEvent.log("auth", "Profile updated", "info", workspace=active_workspace(user))
    return Response(_user_dict(user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_onboarding(request):
    """Mark the setup guide as seen so it stops auto-opening on login."""
    from apps.workspaces.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.onboarding_completed = True
    profile.save(update_fields=["onboarding_completed"])
    return Response({"ok": True})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """Permanently delete the logged-in user's account. Requires their password.

    Workspaces the user was the last member of are deleted too (cascading all their
    mail data); shared workspaces that still have other members are left intact.
    """
    user = request.user
    if not user.check_password(request.data.get("password", "")):
        return Response({"error": "Password is incorrect."}, status=400)

    from apps.workspaces.models import Membership, Workspace  # local: avoid import cycle

    ws_ids = list(Membership.objects.filter(user=user).values_list("workspace_id", flat=True))
    username = user.username
    user.delete()  # cascades memberships, token, profile
    # Remove any workspace that is now memberless (personal ones, or teams they were last in).
    Workspace.objects.filter(id__in=ws_ids, memberships__isnull=True).delete()
    SystemEvent.log("auth", f"Account deleted: {username}", "warning")
    return Response({"ok": True})
