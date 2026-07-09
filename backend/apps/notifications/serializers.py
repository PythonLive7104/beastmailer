from rest_framework import serializers

from .models import TelegramConfig


class TelegramConfigSerializer(serializers.ModelSerializer):
    # Token is write-only; we only report whether one is set.
    bot_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_token = serializers.SerializerMethodField()

    class Meta:
        model = TelegramConfig
        fields = ["enabled", "bot_token", "has_token", "chat_id",
                  "notify_on_sent", "notify_on_received", "notify_on_error", "updated_at"]
        read_only_fields = ["updated_at"]

    def get_has_token(self, obj) -> bool:
        return bool(obj.bot_token_encrypted)

    def update(self, instance, validated_data):
        token = validated_data.pop("bot_token", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if token:
            instance.bot_token = token
        instance.save()
        return instance
