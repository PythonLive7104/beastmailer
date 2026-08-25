from django.contrib import admin
from .models import Mailbox

@admin.register(Mailbox)
class MailboxAdmin(admin.ModelAdmin):
    list_display = ("name", "email_address", "is_active", "scan_spam", "last_polled_at")
    exclude = ("password_encrypted",)
