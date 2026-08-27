from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    complete_onboarding,
    delete_account,
    login,
    logout,
    me,
    register,
    update_profile,
)
from apps.attachments.views import AttachmentViewSet
from apps.billing.views import billing
from apps.campaigns.tracking import track_click, track_open, unsubscribe
from apps.campaigns.views import (
    CampaignSenderViewSet,
    CampaignViewSet,
    ContactListViewSet,
    ContactViewSet,
)
from apps.automation.views import ConfigViewSet, run_engine_now
from apps.core.views import dashboard
from apps.links.views import LinkViewSet, redirect_link
from apps.mail.views import EmailMessageViewSet
from apps.mailboxes.views import MailboxViewSet
from apps.notifications.views import TelegramConfigViewSet
from apps.proxies.views import ProxyViewSet
from apps.rules.views import PlaceholderViewSet, ReplyTemplateViewSet, RuleViewSet
from apps.security.views import SystemEventViewSet, change_password, posture
from apps.workspaces.views import WorkspaceViewSet, accept_invitation

router = DefaultRouter()
router.register("mailboxes", MailboxViewSet)
router.register("rules", RuleViewSet)
router.register("templates", ReplyTemplateViewSet)
router.register("placeholders", PlaceholderViewSet)
router.register("messages", EmailMessageViewSet, basename="messages")
router.register("links", LinkViewSet)
router.register("attachments", AttachmentViewSet)
router.register("proxies", ProxyViewSet)
router.register("campaigns", CampaignViewSet)
router.register("contacts", ContactViewSet)
router.register("contact-lists", ContactListViewSet)
router.register("senders", CampaignSenderViewSet)
router.register("events", SystemEventViewSet)
router.register("workspaces", WorkspaceViewSet, basename="workspaces")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/register/", register),
    path("api/auth/login/", login),
    path("api/auth/logout/", logout),
    path("api/auth/me/", me),
    path("api/auth/profile/", update_profile),
    path("api/auth/onboarding/complete/", complete_onboarding),
    path("api/auth/account/", delete_account),
    path("api/dashboard/", dashboard),
    path("api/billing/", billing),
    # Singleton config: no pk needed — GET reads it, PATCH/PUT update it in place.
    path("api/config/", ConfigViewSet.as_view({"get": "list", "put": "update", "patch": "partial_update"})),
    # Telegram is likewise a per-workspace singleton, plus a /test/ action.
    path("api/telegram/test/", TelegramConfigViewSet.as_view({"post": "test"})),
    path("api/telegram/", TelegramConfigViewSet.as_view({"get": "list", "put": "update", "patch": "partial_update"})),
    path("api/engine/run/", run_engine_now),
    path("api/security/posture/", posture),
    path("api/security/change-password/", change_password),
    path("api/invitations/accept/", accept_invitation),
    path("r/<slug:slug>/", redirect_link),
    # Campaign tracking. Public by design — these are opened from inside a delivered
    # email, so they authenticate with an unguessable token, not a session.
    path("t/o/<str:token>.png", track_open),
    path("t/c/<str:token>/", track_click),
    path("t/u/<str:token>/", unsubscribe),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
