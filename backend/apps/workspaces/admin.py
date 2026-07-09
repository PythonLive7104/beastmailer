from django.contrib import admin
from .models import Invitation, Membership, UserProfile, Workspace


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_personal", "created_at")
    inlines = [MembershipInline]


admin.site.register(Invitation)
admin.site.register(UserProfile)
