import os

from rest_framework import serializers

from .models import Attachment

# Attachments get sent over SMTP, so cap the size (typical mail-server ceiling) and
# refuse executable/script types that have no business being auto-replied to clients.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MB
BLOCKED_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif", ".dll", ".jar",
    ".js", ".jse", ".vbs", ".vbe", ".ps1", ".psm1", ".sh", ".apk", ".app", ".deb",
}


class AttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "name", "file", "file_url", "description", "content_type", "size", "created_at"]
        read_only_fields = ["content_type", "size", "created_at"]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_file(self, upload):
        size = getattr(upload, "size", 0) or 0
        if size > MAX_ATTACHMENT_BYTES:
            raise serializers.ValidationError(
                f"File is too large ({size // (1024 * 1024)} MB). Maximum is "
                f"{MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB."
            )
        ext = os.path.splitext(upload.name or "")[1].lower()
        if ext in BLOCKED_EXTENSIONS:
            raise serializers.ValidationError(f"Files of type '{ext}' can't be used as email attachments.")
        return upload

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def create(self, validated_data):
        upload = validated_data.get("file")
        if upload is not None:
            validated_data["content_type"] = getattr(upload, "content_type", "") or ""
            validated_data["size"] = getattr(upload, "size", 0) or 0
        if not validated_data.get("name") and upload is not None:
            validated_data["name"] = upload.name
        return super().create(validated_data)
