from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import WorkspaceScopedMixin

from .models import Proxy
from .net import test_proxy
from .serializers import ProxySerializer


class ProxyViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Proxy.objects.all()
    serializer_class = ProxySerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Connect out through this proxy and report the exit IP it presents."""
        return Response(test_proxy(self.get_object()))
