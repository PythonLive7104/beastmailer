from rest_framework import serializers

from .models import SystemEvent


class SystemEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemEvent
        fields = ["id", "level", "category", "message", "created_at"]
