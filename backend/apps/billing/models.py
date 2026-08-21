"""Manual crypto paywall.

The superuser sets a monthly fee and a set of wallet addresses in the Django admin.
A user pays off-platform, submits the transaction reference in-app (a `Payment` in
`pending`), and the superuser confirms it — which grants that user a fixed access
window. Access is per user; the engine gates *sending* on the mailbox workspace's
owner having an active window (see apps.billing.services).

Deliberately no payment-gateway integration: confirmation is a human action, so
there is nothing to reconcile and no webhook to secure.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class BillingSettings(models.Model):
    """Singleton: the paywall's global switches, edited in admin."""

    is_enabled = models.BooleanField(
        default=False,
        help_text="Master switch. Off = the whole app is free and nothing is gated.",
    )
    monthly_fee_usd = models.DecimalField(max_digits=8, decimal_places=2, default=30)
    period_days = models.PositiveIntegerField(
        default=30, help_text="How many days a confirmed payment grants."
    )
    instructions = models.TextField(
        blank=True, default="",
        help_text="Shown to users on the payment page, e.g. how to send and what to include.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "billing settings"
        verbose_name_plural = "billing settings"

    def __str__(self):
        return f"Billing (${self.monthly_fee_usd}/mo, {'on' if self.is_enabled else 'off'})"

    @classmethod
    def load(cls) -> "BillingSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)


class CryptoWallet(models.Model):
    """A wallet address users pay to. Managed by the superuser in admin."""

    label = models.CharField(max_length=120, help_text="e.g. 'USDT (TRC20)'")
    currency = models.CharField(max_length=40, help_text="e.g. BTC, ETH, USDT")
    network = models.CharField(max_length=60, blank=True, default="", help_text="e.g. TRC20, ERC20, Bitcoin")
    address = models.CharField(max_length=255)
    memo = models.CharField(max_length=120, blank=True, default="", help_text="Destination tag / memo, if the chain needs one.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} — {self.address}"


class Payment(models.Model):
    """A user's claim that they paid. Starts `pending`; the superuser confirms it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    wallet = models.ForeignKey(CryptoWallet, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount_usd = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=40, blank=True, default="")
    tx_reference = models.CharField(max_length=255, blank=True, default="", help_text="Transaction hash / reference the user provides.")
    note = models.TextField(blank=True, default="")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # The access window this payment grants once confirmed.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="reviewed_payments")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self):
        return f"{self.user} ${self.amount_usd} [{self.status}]"

    def confirm(self, by_user=None):
        """Approve this payment and grant the access window.

        Stacks: if the user already has an active window, extend from its end so a
        second payment adds time rather than overwriting it. Called from the admin
        action, so the two stay in sync.
        """
        settings_obj = BillingSettings.load()
        now = timezone.now()
        current_end = active_period_end(self.user)
        start = current_end if current_end and current_end > now else now
        self.period_start = start
        self.period_end = start + timezone.timedelta(days=settings_obj.period_days)
        self.status = self.Status.CONFIRMED
        self.reviewed_by = by_user
        self.reviewed_at = now
        self.save(update_fields=["period_start", "period_end", "status", "reviewed_by", "reviewed_at"])


def active_period_end(user):
    """The latest confirmed access end for a user, or None if they've never had one."""
    agg = Payment.objects.filter(user=user, status=Payment.Status.CONFIRMED).aggregate(
        last=models.Max("period_end")
    )
    return agg["last"]
