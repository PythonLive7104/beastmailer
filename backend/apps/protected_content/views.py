import io
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import WorkspaceScopedMixin

from .export import build_protected_html
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

    @action(detail=True, methods=["post"])
    def export(self, request, pk=None):
        """Build a standalone protected .html file to host anywhere.

        The page is AES-256-GCM encrypted with a PBKDF2 key from the supplied
        passcode; the file embeds only ciphertext, never the passcode or key.
        An empty passcode produces a keyless (obfuscation-only) file.
        """
        doc = self.get_object()
        if doc.kind != ProtectedDocument.KIND_PAGE:
            return Response(
                {"detail": "Only inline pages can be exported to a standalone HTML file."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        passcode = (request.data.get("passcode") or "").strip()
        html = build_protected_html(doc, passcode=passcode)
        filename = f"{slugify(doc.name) or 'protected'}-protected.html"
        resp = HttpResponse(html, content_type="text/html; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=False, methods=["post"], url_path="export-batch")
    def export_batch(self, request):
        """Export several pages at once as a .zip of protected .html files.

        One passcode applies to all files in the batch. Only inline pages in the
        caller's workspace are included; file-type documents are skipped.
        """
        ids = request.data.get("ids") or []
        passcode = (request.data.get("passcode") or "").strip()
        pages = self.get_queryset().filter(id__in=ids, kind=ProtectedDocument.KIND_PAGE)
        if not pages.exists():
            return Response({"detail": "No exportable pages selected."}, status=status.HTTP_400_BAD_REQUEST)

        buf = io.BytesIO()
        used = {}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in pages:
                base = slugify(doc.name) or f"page-{doc.id}"
                # Guard against duplicate names colliding inside the zip.
                used[base] = used.get(base, 0) + 1
                name = base if used[base] == 1 else f"{base}-{used[base]}"
                zf.writestr(f"{name}-protected.html", build_protected_html(doc, passcode=passcode))

        resp = HttpResponse(buf.getvalue(), content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="protected-pages.zip"'
        return resp
