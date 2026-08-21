from rest_framework import serializers

from .models import Placeholder, ReplyTemplate, Rule


class PlaceholderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Placeholder
        fields = ["id", "key", "label", "description", "static_value", "is_dynamic"]


class ReplyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReplyTemplate
        fields = ["id", "name", "subject", "body", "is_html", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class RuleSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    match_type_display = serializers.CharField(source="get_match_type_display", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A rule can only reference its own workspace's templates/mailboxes/attachments.
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            from apps.workspaces.services import active_workspace
            ws = active_workspace(request.user)
            self.fields["template"].queryset = self.fields["template"].queryset.filter(workspace=ws)
            self.fields["mailboxes"].child_relation.queryset = \
                self.fields["mailboxes"].child_relation.queryset.filter(workspace=ws)
            self.fields["attachments"].child_relation.queryset = \
                self.fields["attachments"].child_relation.queryset.filter(workspace=ws)

    class Meta:
        model = Rule
        fields = [
            "id", "name", "match_type", "match_type_display", "match_value", "case_sensitive",
            "template", "template_name", "mailboxes", "attachments", "is_active", "priority",
            "created_at",
        ]
        read_only_fields = ["created_at"]
