from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.security.models import SystemEvent

from .models import Invitation, Membership, UserProfile, Workspace
from .serializers import InvitationSerializer, MembershipSerializer, WorkspaceSerializer
from .services import active_workspace, can_manage, user_role

User = get_user_model()


class WorkspaceViewSet(viewsets.ModelViewSet):
    """The caller's workspaces, plus member management actions."""

    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        ws = serializer.save()
        Membership.objects.create(workspace=ws, user=self.request.user, role=Membership.Role.OWNER)
        # Switch to the freshly created workspace.
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        profile.current_workspace = ws
        profile.save(update_fields=["current_workspace"])

    def _require_manage(self, ws):
        return can_manage(self.request.user, ws)

    def perform_destroy(self, instance):
        if user_role(self.request.user, instance) != Membership.Role.OWNER:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only the workspace owner can delete it.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def switch(self, request, pk=None):
        """Make this the caller's active workspace."""
        ws = self.get_object()
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.current_workspace = ws
        profile.save(update_fields=["current_workspace"])
        return Response(WorkspaceSerializer(ws, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        ws = self.get_object()
        data = MembershipSerializer(ws.memberships.select_related("user"), many=True).data
        return Response({"members": data, "my_role": user_role(request.user, ws)})

    @action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        """Invite by username/email. Existing users join immediately; otherwise a
        shareable invite code is returned to redeem after signup."""
        ws = self.get_object()
        if not self._require_manage(ws):
            return Response({"error": "Only owners/admins can invite."}, status=403)

        identifier = (request.data.get("identifier") or "").strip()
        role = request.data.get("role", Membership.Role.MEMBER)
        if role not in Membership.Role.values:
            role = Membership.Role.MEMBER
        if not identifier:
            return Response({"error": "Provide a username or email."}, status=400)

        user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if user:
            if Membership.objects.filter(workspace=ws, user=user).exists():
                return Response({"error": "That user is already a member."}, status=400)
            Membership.objects.create(workspace=ws, user=user, role=role)
            SystemEvent.log("team", f"{user.username} added to {ws.name}", "success", workspace=ws)
            return Response({"added": True, "username": user.username}, status=201)

        # No account yet — create an invite code to share.
        invite = Invitation.objects.create(workspace=ws, email=identifier if "@" in identifier else "",
                                            role=role, invited_by=request.user)
        SystemEvent.log("team", f"Invite created for {identifier} to {ws.name}", "info", workspace=ws)
        return Response({"added": False, "invite": InvitationSerializer(invite).data}, status=201)

    @action(detail=True, methods=["post"], url_path="members/(?P<member_id>[^/.]+)/role")
    def set_role(self, request, pk=None, member_id=None):
        ws = self.get_object()
        if not self._require_manage(ws):
            return Response({"error": "Only owners/admins can change roles."}, status=403)
        membership = ws.memberships.filter(id=member_id).first()
        if not membership:
            return Response({"error": "Member not found."}, status=404)
        if membership.role == Membership.Role.OWNER:
            return Response({"error": "Can't change the owner's role."}, status=400)
        role = request.data.get("role")
        if role not in Membership.Role.values:
            return Response({"error": "Invalid role."}, status=400)
        membership.role = role
        membership.save(update_fields=["role"])
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["delete"], url_path="members/(?P<member_id>[^/.]+)")
    def remove_member(self, request, pk=None, member_id=None):
        ws = self.get_object()
        membership = ws.memberships.filter(id=member_id).first()
        if not membership:
            return Response({"error": "Member not found."}, status=404)
        # You can always remove yourself (leave); otherwise you must be a manager.
        if membership.user_id != request.user.id and not self._require_manage(ws):
            return Response({"error": "Only owners/admins can remove members."}, status=403)
        if membership.role == Membership.Role.OWNER:
            return Response({"error": "The owner can't be removed. Transfer or delete the workspace."}, status=400)
        membership.delete()
        SystemEvent.log("team", f"{membership.user.username} left/removed from {ws.name}", "warning", workspace=ws)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def accept_invitation(request):
    """Redeem an invite code to join its workspace."""
    code = (request.data.get("code") or "").strip()
    invite = Invitation.objects.filter(code=code, accepted=False).select_related("workspace").first()
    if not invite:
        return Response({"error": "Invalid or already-used invite code."}, status=400)
    ws = invite.workspace
    Membership.objects.get_or_create(workspace=ws, user=request.user, defaults={"role": invite.role})
    invite.accepted = True
    invite.save(update_fields=["accepted"])
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.current_workspace = ws
    profile.save(update_fields=["current_workspace"])
    SystemEvent.log("team", f"{request.user.username} joined {ws.name} via invite", "success", workspace=ws)
    return Response({"joined": True, "workspace": WorkspaceSerializer(ws, context={"request": request}).data})
