from django.utils.crypto import get_random_string
from rest_framework import serializers

from .models import ProtectedAccessLog, ProtectedAsset, ProtectedDocument

# Payload is stored encrypted in the DB, so keep it to a sane size.
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
_SLUG_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


class ProtectedDocumentSerializer(serializers.ModelSerializer):
    # Write-only payload inputs: an uploaded file (kind="file") or inline HTML
    # (kind="page"). Neither is ever echoed back; only metadata is readable.
    upload = serializers.FileField(write_only=True, required=False)
    html = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    # Passcode is set/changed here but never returned. clear_passcode removes it.
    passcode = serializers.CharField(write_only=True, required=False, allow_blank=True)
    clear_passcode = serializers.BooleanField(write_only=True, required=False, default=False)

    requires_passcode = serializers.BooleanField(read_only=True)
    public_path = serializers.SerializerMethodField()

    class Meta:
        model = ProtectedDocument
        fields = [
            "id", "name", "slug", "kind",
            "upload", "html", "passcode", "clear_passcode",
            "content_type", "size", "requires_passcode",
            "expires_at", "max_views", "view_count", "allowed_referrers", "is_active",
            "disable_right_click", "disable_copy", "disable_print",
            "block_shortcuts", "minify", "wrong_passcode_action",
            "public_path", "created_at", "updated_at",
        ]
        read_only_fields = ["content_type", "size", "view_count", "created_at", "updated_at"]
        extra_kwargs = {
            # Slug is optional on input; we generate an unguessable one if omitted.
            "slug": {"required": False},
        }

    def get_public_path(self, obj) -> str:
        return f"/g/{obj.slug}/"

    def validate_upload(self, upload):
        size = getattr(upload, "size", 0) or 0
        if size > MAX_PAYLOAD_BYTES:
            raise serializers.ValidationError(
                f"File is too large ({size // (1024 * 1024)} MB). Maximum is "
                f"{MAX_PAYLOAD_BYTES // (1024 * 1024)} MB."
            )
        return upload

    def validate(self, attrs):
        # On create, the document needs a payload. On update, leaving both out
        # keeps the existing content.
        if self.instance is None and "upload" not in attrs and "html" not in attrs:
            raise serializers.ValidationError("Provide either 'upload' (a file) or 'html' (inline page content).")
        return attrs

    def _unique_slug(self) -> str:
        for _ in range(10):
            slug = get_random_string(12, _SLUG_ALPHABET)
            if not ProtectedDocument.objects.filter(slug=slug).exists():
                return slug
        raise serializers.ValidationError("Could not allocate a unique slug; please retry.")

    def _apply_payload_and_secrets(self, instance, validated_data):
        """Move the write-only fields onto the instance (encrypting the payload)."""
        upload = validated_data.pop("upload", None)
        html = validated_data.pop("html", None)
        passcode = validated_data.pop("passcode", None)
        clear_passcode = validated_data.pop("clear_passcode", False)

        if upload is not None:
            instance.kind = ProtectedDocument.KIND_FILE
            instance.content_type = getattr(upload, "content_type", "") or "application/octet-stream"
            instance.set_payload(upload.read())
        elif html is not None:
            instance.kind = ProtectedDocument.KIND_PAGE
            instance.content_type = "text/html; charset=utf-8"
            instance.set_payload(html.encode("utf-8"))

        if clear_passcode:
            instance.set_passcode("")
        elif passcode:
            instance.set_passcode(passcode)

        return instance

    def create(self, validated_data):
        if not validated_data.get("slug"):
            validated_data["slug"] = self._unique_slug()
        # workspace is injected by WorkspaceScopedMixin.perform_create via save().
        instance = ProtectedDocument(**{
            k: v for k, v in validated_data.items()
            if k not in ("upload", "html", "passcode", "clear_passcode")
        })
        self._apply_payload_and_secrets(instance, validated_data)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        self._apply_payload_and_secrets(instance, validated_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ProtectedAssetSerializer(serializers.ModelSerializer):
    upload = serializers.FileField(write_only=True)
    gated_path = serializers.SerializerMethodField()

    class Meta:
        model = ProtectedAsset
        fields = ["id", "name", "upload", "content_type", "size", "gated_path", "created_at"]
        read_only_fields = ["content_type", "size", "created_at"]

    def get_gated_path(self, obj) -> str:
        return f"/g/{obj.document.slug}/asset/{obj.id}/"

    def validate_upload(self, upload):
        size = getattr(upload, "size", 0) or 0
        if size > MAX_PAYLOAD_BYTES:
            raise serializers.ValidationError(
                f"Asset is too large ({size // (1024 * 1024)} MB). Maximum is "
                f"{MAX_PAYLOAD_BYTES // (1024 * 1024)} MB."
            )
        return upload

    def create(self, validated_data):
        upload = validated_data.pop("upload")
        asset = ProtectedAsset(
            document=validated_data["document"],
            name=validated_data.get("name") or upload.name,
            content_type=getattr(upload, "content_type", "") or "application/octet-stream",
        )
        asset.set_payload(upload.read())
        asset.save()
        return asset


class ProtectedAccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProtectedAccessLog
        fields = ["id", "outcome", "ip", "referrer", "created_at"]
        read_only_fields = fields
