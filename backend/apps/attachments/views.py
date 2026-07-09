from rest_framework import viewsets

from apps.core.mixins import WorkspaceScopedMixin

from .models import Attachment
from .serializers import AttachmentSerializer


class AttachmentViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
