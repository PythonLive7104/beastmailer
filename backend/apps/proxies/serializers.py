from rest_framework import serializers

from .models import Proxy


class ProxySerializer(serializers.ModelSerializer):
    # Password is write-only: accepted on create/update, never returned.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = Proxy
        fields = [
            "id", "label", "kind", "host", "port",
            "username", "password", "has_password",
            "is_active", "last_used_at", "last_error", "failure_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["last_used_at", "last_error", "failure_count", "created_at", "updated_at"]

    def get_has_password(self, obj) -> bool:
        return bool(obj.password_encrypted)

    def create(self, validated_data):
        raw = validated_data.pop("password", "")
        proxy = Proxy(**validated_data)
        if raw:
            proxy.password = raw
        proxy.save()
        return proxy

    def update(self, instance, validated_data):
        raw = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if raw:  # only overwrite when a new password is supplied
            instance.password = raw
        instance.save()
        return instance
