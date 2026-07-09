from rest_framework import mixins, viewsets

from apps.workspaces.services import active_workspace

from .models import EmailMessage
from .serializers import EmailMessageSerializer


class EmailMessageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only feed of sent/received/scheduled mail.

    Filterable via ?direction=, ?status=, ?mailbox=, ?thread_key=, ?search=.
    """

    serializer_class = EmailMessageSerializer

    def get_queryset(self):
        qs = EmailMessage.objects.select_related("mailbox").filter(workspace=active_workspace(self.request.user))
        params = self.request.query_params
        if direction := params.get("direction"):
            qs = qs.filter(direction=direction)
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if mailbox := params.get("mailbox"):
            qs = qs.filter(mailbox_id=mailbox)
        if thread_key := params.get("thread_key"):
            qs = qs.filter(thread_key=thread_key)
        if search := params.get("search"):
            qs = qs.filter(subject__icontains=search)
        return qs
