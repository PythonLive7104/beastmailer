from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.automation.engine import render_template
from apps.core.mixins import WorkspaceScopedMixin

from .models import Placeholder, ReplyTemplate, Rule
from .serializers import PlaceholderSerializer, ReplyTemplateSerializer, RuleSerializer


class PlaceholderViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Placeholder.objects.all()
    serializer_class = PlaceholderSerializer


class ReplyTemplateViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = ReplyTemplate.objects.all()
    serializer_class = ReplyTemplateSerializer

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Render this template against sample context so the user sees the result."""
        template = self.get_object()
        context = {
            "sender_name": "Jane Doe",
            "sender_email": "jane.doe@example.com",
            "original_subject": "Project Inquiry: New warehouse build",
            "mailbox_name": "Sales inbox",
            "date": "Thursday, July 02, 2026",
        }
        return Response({
            "subject": render_template(template.subject, context, workspace=template.workspace),
            "body": render_template(template.body, context, workspace=template.workspace),
            "is_html": template.is_html,
        })


class RuleViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Rule.objects.select_related("template").prefetch_related("mailboxes").all()
    serializer_class = RuleSerializer

    @action(detail=False, methods=["post"])
    def test_match(self, request):
        """Given a subject, return which rule (if any) would fire."""
        subject = request.data.get("subject", "")
        for rule in self.get_queryset().filter(is_active=True).order_by("priority", "name"):
            if rule.matches(subject):
                return Response({"matched": True, "rule": RuleSerializer(rule).data})
        return Response({"matched": False, "rule": None})
