from rest_framework import serializers

from .models import EmailMessage


class EmailMessageSerializer(serializers.ModelSerializer):
    mailbox_name = serializers.CharField(source="mailbox.name", read_only=True)
    event = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()

    class Meta:
        model = EmailMessage
        fields = [
            "id", "mailbox", "mailbox_name", "direction", "status", "event",
            "subject", "thread_key", "from_addr", "from_name", "to_addr", "body", "is_html",
            "matched_rule", "reply_to_message",
            "scheduled_for", "received_at", "sent_at", "timestamp", "error", "created_at",
        ]

    def get_event(self, obj) -> str:
        # The dashboard labels rows by what happened: received / scheduled / sent.
        return obj.status

    def get_timestamp(self, obj):
        return obj.sent_at or obj.received_at or obj.scheduled_for or obj.created_at
