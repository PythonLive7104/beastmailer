from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.automation.models import Config
from apps.mail.models import EmailMessage
from apps.mail.serializers import EmailMessageSerializer
from apps.mailboxes.models import Mailbox
from apps.rules.models import Rule
from apps.workspaces.services import active_workspace


@api_view(["GET"])
def dashboard(request):
    """Aggregate stats + recent activity for the active workspace's dashboard."""
    ws = active_workspace(request.user)
    config = Config.load(ws)
    mailboxes = Mailbox.objects.filter(workspace=ws)
    messages = EmailMessage.objects.filter(workspace=ws)

    recent = messages.select_related("mailbox")[:50]

    return Response({
        "mailboxes": {"active": mailboxes.filter(is_active=True).count(), "total": mailboxes.count()},
        "auto_reply": {
            "enabled": config.auto_reply_enabled,
            "reply_delay_minutes": config.reply_delay_minutes,
        },
        "poll_interval_seconds": config.poll_interval_seconds,
        "reply_delay_minutes": config.reply_delay_minutes,
        "counts": {
            "sent": messages.filter(status=EmailMessage.Status.SENT).count(),
            "received": messages.filter(status=EmailMessage.Status.RECEIVED).count(),
            "scheduled": messages.filter(status=EmailMessage.Status.SCHEDULED).count(),
            "failed": messages.filter(status=EmailMessage.Status.FAILED).count(),
            "rules": Rule.objects.filter(workspace=ws, is_active=True).count(),
        },
        "recent_activity": EmailMessageSerializer(recent, many=True).data,
    })
