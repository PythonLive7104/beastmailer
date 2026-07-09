from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.automation.engine import poll_mailbox, test_connection
from apps.core.mixins import WorkspaceScopedMixin

from .models import Mailbox
from .serializers import MailboxSerializer


class MailboxViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Mailbox.objects.all()
    serializer_class = MailboxSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Verify IMAP + SMTP login for this mailbox."""
        result = test_connection(self.get_object())
        return Response(result)

    @action(detail=True, methods=["post"])
    def poll(self, request, pk=None):
        """Trigger an immediate poll of this mailbox."""
        mailbox = self.get_object()
        try:
            ingested = poll_mailbox(mailbox)
            return Response({"ok": True, "ingested": ingested})
        except Exception as exc:  # noqa: BLE001
            return Response({"ok": False, "error": str(exc)}, status=400)
