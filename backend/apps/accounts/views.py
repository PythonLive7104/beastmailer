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


def _user_payload(user, token):
    ws = active_workspace(user)
    return {
        "token": token.key,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "workspace": {"id": ws.id, "name": ws.name} if ws else None,
        },
    }


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
    user = request.user
    ws = active_workspace(user)
    return Response({
        "id": user.id, "username": user.username, "email": user.email, "is_staff": user.is_staff,
        "workspace": {"id": ws.id, "name": ws.name} if ws else None,
    })
