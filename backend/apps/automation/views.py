from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.automation.engine import run_once
from apps.workspaces.services import active_workspace

from .models import Config
from .serializers import ConfigSerializer


class ConfigViewSet(viewsets.ViewSet):
    """Singleton config exposed at /api/config/ (GET) and updated via PATCH/PUT."""

    def list(self, request):
        return Response(ConfigSerializer(Config.load(active_workspace(request.user))).data)

    def _update(self, request, partial):
        serializer = ConfigSerializer(Config.load(active_workspace(request.user)), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def update(self, request, pk=None):
        return self._update(request, partial=False)

    def partial_update(self, request, pk=None):
        return self._update(request, partial=True)


@api_view(["POST"])
def run_engine_now(request):
    """Kick a single engine tick on demand, scoped to the caller's workspace."""
    return Response(run_once(workspace=active_workspace(request.user)))
