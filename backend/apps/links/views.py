from django.db.models import F
from django.shortcuts import get_object_or_404, redirect
from rest_framework import viewsets

from apps.core.mixins import WorkspaceScopedMixin

from .models import Link
from .serializers import LinkSerializer


class LinkViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Link.objects.all()
    serializer_class = LinkSerializer


def redirect_link(request, slug):
    """Public endpoint: count a click and forward to the target URL."""
    link = get_object_or_404(Link, slug=slug, is_active=True)
    Link.objects.filter(pk=link.pk).update(clicks=F("clicks") + 1)
    return redirect(link.url)
