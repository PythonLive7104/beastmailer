from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import mixins, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.mailboxes.models import Mailbox
from apps.workspaces.services import active_workspace

from .models import SystemEvent
from .serializers import SystemEventSerializer


class SystemEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = SystemEvent.objects.all()
    serializer_class = SystemEventSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(workspace=active_workspace(self.request.user))
        if level := self.request.query_params.get("level"):
            qs = qs.filter(level=level)
        return qs


@api_view(["GET"])
def posture(request):
    """Security posture summary for the active workspace's dashboard cards."""
    ws = active_workspace(request.user)
    mailboxes = Mailbox.objects.filter(workspace=ws)
    without_pw = [m.name for m in mailboxes if not m.password_encrypted]
    return Response({
        "encryption": {
            "at_rest": True,
            "algorithm": "Fernet (AES-128-CBC + HMAC)",
            "dedicated_key": bool(settings.ENCRYPTION_KEY),  # False = derived from SECRET_KEY (dev)
        },
        "debug_mode": settings.DEBUG,
        "mailboxes_total": mailboxes.count(),
        "mailboxes_missing_password": without_pw,
        "recent_errors": SystemEvent.objects.filter(workspace=ws, level="error").count(),
    })


@api_view(["POST"])
def change_password(request):
    """Change the logged-in user's own password. Body: {current_password, new_password}."""
    user = request.user
    current_password = request.data.get("current_password", "")
    new_password = request.data.get("new_password", "")
    if not user.check_password(current_password):
        SystemEvent.log("auth", "Password change rejected: wrong current password", "warning",
                        workspace=active_workspace(user))
        return Response({"ok": False, "error": "Current password is incorrect."}, status=400)
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        return Response({"ok": False, "error": " ".join(exc.messages)}, status=400)
    user.set_password(new_password)
    user.save()
    # Rotate the auth token so the change takes effect everywhere.
    Token.objects.filter(user=user).delete()
    new_token = Token.objects.create(user=user)
    SystemEvent.log("auth", "Password changed", "warning", workspace=active_workspace(user))
    return Response({"ok": True, "token": new_token.key})
