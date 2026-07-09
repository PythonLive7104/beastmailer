from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.workspaces.services import active_workspace

from .models import TelegramConfig
from .serializers import TelegramConfigSerializer
from .telegram import send_message


class TelegramConfigViewSet(viewsets.ViewSet):
    """Singleton Telegram config at /api/telegram/ with a /test/ action."""

    def list(self, request):
        return Response(TelegramConfigSerializer(TelegramConfig.load(active_workspace(request.user))).data)

    def _update(self, request, partial):
        serializer = TelegramConfigSerializer(TelegramConfig.load(active_workspace(request.user)), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def update(self, request, pk=None):
        return self._update(request, partial=False)

    def partial_update(self, request, pk=None):
        return self._update(request, partial=True)

    @action(detail=False, methods=["post"])
    def test(self, request):
        """Send a test message. Uses a token from the request if provided, else the saved one."""
        cfg = TelegramConfig.load(active_workspace(request.user))
        token = request.data.get("bot_token") or cfg.bot_token
        chat_id = request.data.get("chat_id") or cfg.chat_id
        ok, err = send_message(token, chat_id, "✅ <b>BeastMailer Auto-Reply</b> test message — Telegram is connected.")
        return Response({"ok": ok, "error": err}, status=200 if ok else 400)
