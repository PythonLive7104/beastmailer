from django.contrib import admin

from .models import ProtectedAccessLog, ProtectedAsset, ProtectedDocument


@admin.register(ProtectedDocument)
class ProtectedDocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "workspace", "is_active", "view_count", "created_at")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug")
    # Ciphertext and passcode hash are never meant to be eyeballed or edited here.
    exclude = ("ciphertext", "passcode_hash")


@admin.register(ProtectedAsset)
class ProtectedAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "document", "content_type", "size", "created_at")
    exclude = ("ciphertext",)


@admin.register(ProtectedAccessLog)
class ProtectedAccessLogAdmin(admin.ModelAdmin):
    list_display = ("document", "outcome", "ip", "created_at")
    list_filter = ("outcome",)
