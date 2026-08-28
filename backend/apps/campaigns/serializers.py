from rest_framework import serializers

from .models import Campaign, CampaignRecipient, CampaignSender, Contact, ContactList


class ContactSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    list_ids = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True, source="lists"
    )

    class Meta:
        model = Contact
        fields = [
            "id", "email", "first_name", "last_name", "company", "fields",
            "status", "status_reason", "full_name", "list_ids",
            "unsubscribed_at", "created_at",
        ]
        read_only_fields = ["status_reason", "unsubscribed_at", "created_at"]


class ContactListSerializer(serializers.ModelSerializer):
    contact_count = serializers.SerializerMethodField()
    mailable_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContactList
        fields = ["id", "name", "description", "contact_count", "mailable_count", "created_at"]

    def get_contact_count(self, obj) -> int:
        return obj.contacts.count()

    def validate_name(self, value):
        """Two lists with the same name are indistinguishable in every picker in the
        app, so refuse the duplicate rather than letting people guess later."""
        name = (value or "").strip()
        qs = ContactList.objects.filter(name__iexact=name)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
            qs = qs.filter(workspace=self.instance.workspace)
        else:
            from apps.workspaces.services import active_workspace
            qs = qs.filter(workspace=active_workspace(self.context["request"].user))
        if qs.exists():
            raise serializers.ValidationError(f"You already have a list called “{name}”.")
        return name


class CampaignSenderSerializer(serializers.ModelSerializer):
    # Write-only, like Mailbox.password: accepted on save, never echoed back.
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_secret = serializers.SerializerMethodField()
    sender_email = serializers.CharField(read_only=True)
    remaining_today = serializers.SerializerMethodField()
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    authorized_domain_list = serializers.ListField(read_only=True)

    class Meta:
        model = CampaignSender
        fields = [
            "id", "name", "kind", "kind_display", "mailbox",
            "from_email", "from_name", "reply_to", "sender_email",
            "smtp_host", "smtp_port", "smtp_use_tls", "username", "secret", "has_secret",
            "region", "domain",
            "daily_limit", "hourly_limit", "weight", "is_overflow", "use_proxy",
            "use_for_replies", "authorized_domains", "authorized_domain_list",
            "reply_identity", "is_active",
            "sent_today", "sent_this_hour", "remaining_today", "last_error", "created_at",
        ]
        read_only_fields = ["sent_today", "sent_this_hour", "last_error", "created_at"]

    def get_has_secret(self, obj) -> bool:
        return bool(obj.secret_encrypted)

    def get_remaining_today(self, obj):
        return obj.remaining_today()

    def validate(self, attrs):
        """Reject routes that cannot possibly send, rather than failing mid-campaign."""
        kind = attrs.get("kind", getattr(self.instance, "kind", CampaignSender.Kind.MAILBOX))
        mailbox = attrs.get("mailbox", getattr(self.instance, "mailbox", None))
        from_email = attrs.get("from_email", getattr(self.instance, "from_email", ""))
        if kind == CampaignSender.Kind.MAILBOX:
            if not mailbox:
                raise serializers.ValidationError({"mailbox": "Pick a mailbox for this route."})
        else:
            if not from_email:
                raise serializers.ValidationError(
                    {"from_email": "External providers need the address to send from."}
                )
            if kind == CampaignSender.Kind.SMTP:
                host = attrs.get("smtp_host", getattr(self.instance, "smtp_host", ""))
                if not host:
                    raise serializers.ValidationError({"smtp_host": "SMTP host is required."})
        return attrs

    def create(self, validated_data):
        raw = validated_data.pop("secret", "")
        sender = CampaignSender(**validated_data)
        if raw:
            sender.secret = raw
        sender.save()
        return sender

    def update(self, instance, validated_data):
        raw = validated_data.pop("secret", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if raw:  # blank means "leave the stored credential alone"
            instance.secret = raw
        instance.save()
        return instance


class CampaignSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    audience_size = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "subject", "body", "is_html", "preheader",
            "lists", "senders", "attachments",
            "status", "scheduled_for", "per_tick_limit",
            "track_opens", "track_clicks",
            "started_at", "finished_at", "error",
            "stats", "audience_size", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "started_at", "finished_at", "error", "created_at", "updated_at"]

    def get_stats(self, obj) -> dict:
        # Reads the viewset's annotations when present; falls back to a single
        # aggregate for the detail view and anywhere else this serializer is used.
        return obj.stats()

    def get_audience_size(self, obj) -> int:
        """How many contacts this campaign would send to if it started now."""
        sizes = self.context.get("audience_sizes")
        if sizes is not None:
            return sizes.get(obj.id, 0)
        return (
            Contact.objects.filter(lists__in=obj.lists.all(), status=Contact.Status.SUBSCRIBED)
            .distinct()
            .count()
        )


class CampaignRecipientSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="contact.email", read_only=True)
    name = serializers.CharField(source="contact.full_name", read_only=True)
    sender_name = serializers.CharField(source="sender.name", read_only=True, default="")

    class Meta:
        model = CampaignRecipient
        fields = [
            "id", "email", "name", "status", "sender_name",
            "sent_at", "opened_at", "open_count", "clicked_at", "click_count",
            "unsubscribed_at", "attempt_count", "error",
        ]
