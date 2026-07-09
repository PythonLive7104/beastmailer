from django.contrib import admin

from .models import Proxy


@admin.register(Proxy)
class ProxyAdmin(admin.ModelAdmin):
    list_display = ("label", "kind", "host", "port", "is_active", "workspace", "last_used_at")
    list_filter = ("kind", "is_active")
    search_fields = ("label", "host")
