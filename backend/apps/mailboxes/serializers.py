from rest_framework import serializers

from .models import Mailbox


class MailboxSerializer(serializers.ModelSerializer):
    # Password is write-only: accepted on create/update, never returned.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = Mailbox
        fields = [
            "id", "name", "email_address",
            "imap_host", "imap_port", "imap_use_ssl",
            "smtp_host", "smtp_port", "smtp_use_tls",
            "username", "password", "has_password",
            "is_active", "use_proxy", "last_polled_at", "last_seen_uid", "last_error",
            "created_at", "updated_at",
        ]
        read_only_fields = ["last_polled_at", "last_seen_uid", "last_error", "created_at", "updated_at"]

    def get_has_password(self, obj) -> bool:
        return bool(obj.password_encrypted)

    def create(self, validated_data):
        raw = validated_data.pop("password", "")
        mailbox = Mailbox(**validated_data)
        if raw:
            mailbox.password = raw
        mailbox.save()
        return mailbox

    def update(self, instance, validated_data):
        raw = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if raw:  # only overwrite when a new password is supplied
            instance.password = raw
        instance.save()
        return instance
