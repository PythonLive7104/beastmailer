from rest_framework import serializers

from .models import CryptoWallet, Payment


class CryptoWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = CryptoWallet
        fields = ["id", "label", "currency", "network", "address", "memo"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id", "amount_usd", "currency", "wallet", "tx_reference", "note",
            "status", "period_start", "period_end", "created_at", "reviewed_at",
        ]
        read_only_fields = ["status", "period_start", "period_end", "created_at", "reviewed_at"]
