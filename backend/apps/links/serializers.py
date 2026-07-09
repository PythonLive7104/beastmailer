from rest_framework import serializers

from .models import Link


class LinkSerializer(serializers.ModelSerializer):
    tracking_path = serializers.SerializerMethodField()

    class Meta:
        model = Link
        fields = ["id", "name", "slug", "url", "description", "clicks", "is_active",
                  "tracking_path", "created_at"]
        read_only_fields = ["clicks", "created_at"]

    def get_tracking_path(self, obj) -> str:
        return f"/r/{obj.slug}/"
