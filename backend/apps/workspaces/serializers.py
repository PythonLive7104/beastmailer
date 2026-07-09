from rest_framework import serializers

from .models import Invitation, Membership, Workspace


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "username", "email", "role", "created_at"]
        read_only_fields = ["user", "created_at"]


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "is_personal", "role", "member_count", "is_current", "created_at"]
        read_only_fields = ["is_personal", "created_at"]

    def _user(self):
        request = self.context.get("request")
        return request.user if request else None

    def get_role(self, obj):
        user = self._user()
        m = obj.memberships.filter(user=user).first() if user else None
        return m.role if m else None

    def get_member_count(self, obj) -> int:
        return obj.memberships.count()

    def get_is_current(self, obj) -> bool:
        user = self._user()
        profile = getattr(user, "profile", None) if user else None
        return bool(profile and profile.current_workspace_id == obj.id)


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "code", "accepted", "created_at"]
        read_only_fields = ["code", "accepted", "created_at"]
