from django.contrib import admin
from .models import SystemEvent

@admin.register(SystemEvent)
class SystemEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "level", "category", "message")
    list_filter = ("level", "category")
