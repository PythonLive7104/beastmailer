from django.contrib import admin
from .models import EmailMessage

@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "direction", "status", "from_addr", "to_addr", "created_at")
    list_filter = ("direction", "status", "mailbox")
