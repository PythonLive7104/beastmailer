from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import WorkspaceScopedMixin

from .models import ProtectedAsset, ProtectedDocument
from .serializers import (
    ProtectedAccessLogSerializer,
    ProtectedAssetSerializer,
    ProtectedDocumentSerializer,
)


class ProtectedDocumentViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = ProtectedDocument.objects.all()
    serializer_class = ProtectedDocumentSerializer

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """Immediately stop serving this document."""
        doc = self.get_object()
        doc.is_active = False
        doc.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Re-enable a revoked document."""
        doc = self.get_object()
        doc.is_active = True
        doc.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["post"], url_path="reset-views")
    def reset_views(self, request, pk=None):
        """Reset the view counter (e.g. after raising max_views)."""
        doc = self.get_object()
        doc.view_count = 0
        doc.save(update_fields=["view_count", "updated_at"])
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["get"], url_path="access-log")
    def access_log(self, request, pk=None):
        """Recent access attempts for this document."""
        doc = self.get_object()
        logs = doc.access_logs.all()[:200]
        return Response(ProtectedAccessLogSerializer(logs, many=True).data)

    @action(detail=True, methods=["get", "post"])
    def assets(self, request, pk=None):
        """List this document's gated assets, or upload a new one."""
        doc = self.get_object()
        if request.method == "POST":
            ser = ProtectedAssetSerializer(data=request.data, context={"request": request})
            ser.is_valid(raise_exception=True)
            ser.save(document=doc)
            return Response(ser.data, status=status.HTTP_201_CREATED)
        qs = doc.assets.all()
        return Response(ProtectedAssetSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=True, methods=["delete"], url_path=r"assets/(?P<asset_id>[^/.]+)")
    def delete_asset(self, request, pk=None, asset_id=None):
        doc = self.get_object()
        asset = get_object_or_404(ProtectedAsset, pk=asset_id, document=doc)
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
