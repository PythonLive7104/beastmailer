from django.contrib import admin
from django.utils import timezone

from .models import BillingSettings, CryptoWallet, Payment


@admin.register(BillingSettings)
class BillingSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_enabled", "monthly_fee_usd", "period_days", "updated_at")

    def has_add_permission(self, request):
        # Singleton: edit the one row, never add a second.
        return not BillingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CryptoWallet)
class CryptoWalletAdmin(admin.ModelAdmin):
    list_display = ("label", "currency", "network", "address", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("label", "address")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "amount_usd", "currency", "status", "period_end", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "tx_reference")
    readonly_fields = ("period_start", "period_end", "reviewed_by", "reviewed_at", "created_at")
    actions = ("confirm_payments", "reject_payments")

    @admin.action(description="Confirm selected payments (grant access)")
    def confirm_payments(self, request, queryset):
        n = 0
        for payment in queryset.exclude(status=Payment.Status.CONFIRMED):
            payment.confirm(by_user=request.user)
            n += 1
        self.message_user(request, f"Confirmed {n} payment(s).")

    @admin.action(description="Reject selected payments")
    def reject_payments(self, request, queryset):
        updated = queryset.exclude(status=Payment.Status.CONFIRMED).update(
            status=Payment.Status.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now()
        )
        self.message_user(request, f"Rejected {updated} payment(s).")
