from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import BillingSettings, CryptoWallet, Payment, active_period_end
from .serializers import CryptoWalletSerializer, PaymentSerializer
from .services import billing_enabled, user_is_subscribed


@api_view(["GET", "POST"])
def billing(request):
    """GET: the caller's subscription status + how to pay.
    POST: submit a payment claim (creates a pending Payment)."""
    settings_obj = BillingSettings.load()
    if request.method == "POST":
        data = request.data
        payment = Payment.objects.create(
            user=request.user,
            amount_usd=data.get("amount_usd") or settings_obj.monthly_fee_usd,
            currency=(data.get("currency") or "").strip(),
            wallet_id=data.get("wallet") or None,
            tx_reference=(data.get("tx_reference") or "").strip(),
            note=(data.get("note") or "").strip(),
        )
        return Response(PaymentSerializer(payment).data, status=201)

    return Response({
        "enabled": billing_enabled(),
        "active": user_is_subscribed(request.user),
        "exempt": bool(request.user.is_staff or request.user.is_superuser),
        "expires_at": active_period_end(request.user),
        "fee_usd": settings_obj.monthly_fee_usd,
        "period_days": settings_obj.period_days,
        "instructions": settings_obj.instructions,
        "wallets": CryptoWalletSerializer(
            CryptoWallet.objects.filter(is_active=True), many=True
        ).data,
        "payments": PaymentSerializer(
            Payment.objects.filter(user=request.user)[:20], many=True
        ).data,
    })
