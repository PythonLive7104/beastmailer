import csv
import io

from django.db import models
from django.utils import timezone
from rest_framework import status as http, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import WorkspaceScopedMixin

from .models import Campaign, CampaignRecipient, CampaignSender, Contact, ContactList
from .runner import materialise, send_campaign_batch
from .sending import build_body, recipient_context, send_test
from .serializers import (
    CampaignRecipientSerializer,
    CampaignSenderSerializer,
    CampaignSerializer,
    ContactListSerializer,
    ContactSerializer,
)

# Columns we map onto real fields; anything else is kept in Contact.fields and
# stays available to templates as its own {{tag}}.
_KNOWN_COLUMNS = {
    "email": "email", "e-mail": "email", "email address": "email",
    "first name": "first_name", "firstname": "first_name", "first": "first_name",
    "last name": "last_name", "lastname": "last_name", "last": "last_name", "surname": "last_name",
    "company": "company", "organisation": "company", "organization": "company",
}


class ContactViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (state := params.get("status")):
            qs = qs.filter(status=state)
        if (list_id := params.get("list")):
            qs = qs.filter(lists__id=list_id)
        if (search := params.get("search")):
            qs = qs.filter(
                models.Q(email__icontains=search)
                | models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(company__icontains=search)
            )
        return qs.distinct()

    @action(detail=False, methods=["post"])
    def import_csv(self, request):
        """Bulk-import contacts from pasted CSV text, optionally onto a list.

        Re-importing an address updates that contact instead of duplicating it, and
        never revives one that unsubscribed — honouring an opt-out is the whole point
        of storing it.
        """
        raw = request.data.get("csv", "")
        list_id = request.data.get("list")
        if not raw.strip():
            return Response({"detail": "No CSV supplied."}, status=http.HTTP_400_BAD_REQUEST)

        workspace = self.get_workspace()
        target_list = None
        if list_id:
            target_list = ContactList.objects.filter(workspace=workspace, pk=list_id).first()
            if target_list is None:
                return Response({"detail": "List not found."}, status=http.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(raw.strip()))
        if not reader.fieldnames:
            return Response({"detail": "CSV has no header row."}, status=http.HTTP_400_BAD_REQUEST)

        mapping = {name: _KNOWN_COLUMNS.get((name or "").strip().lower()) for name in reader.fieldnames}
        if "email" not in mapping.values():
            return Response(
                {"detail": "CSV needs an 'email' column."}, status=http.HTTP_400_BAD_REQUEST
            )

        created = updated = skipped = 0
        touched: list[Contact] = []
        for row in reader:
            attrs, extra = {}, {}
            for column, value in row.items():
                field = mapping.get(column)
                if field:
                    attrs[field] = (value or "").strip()
                elif column:
                    extra[column.strip()] = (value or "").strip()
            email = (attrs.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue

            contact, was_created = Contact.objects.get_or_create(
                workspace=workspace, email=email,
                defaults={k: v for k, v in attrs.items() if k != "email"} | {"fields": extra},
            )
            if was_created:
                created += 1
            else:
                for field, value in attrs.items():
                    if field != "email" and value:
                        setattr(contact, field, value)
                if extra:
                    contact.fields = {**(contact.fields or {}), **extra}
                contact.save()
                updated += 1
            touched.append(contact)

        if target_list and touched:
            target_list.contacts.add(*touched)

        return Response({
            "created": created, "updated": updated, "skipped": skipped,
            "list": target_list.name if target_list else None,
        })

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Add/remove a set of contacts to a list, or change their status."""
        ids = request.data.get("ids") or []
        op = request.data.get("op")
        contacts = self.get_queryset().filter(id__in=ids)
        if op in {"add_to_list", "remove_from_list"}:
            target = ContactList.objects.filter(workspace=self.get_workspace(),
                                                pk=request.data.get("list")).first()
            if target is None:
                return Response({"detail": "List not found."}, status=http.HTTP_400_BAD_REQUEST)
            if op == "add_to_list":
                target.contacts.add(*contacts)
            else:
                target.contacts.remove(*contacts)
        elif op == "unsubscribe":
            contacts.update(status=Contact.Status.UNSUBSCRIBED,
                            status_reason="Unsubscribed by an admin",
                            unsubscribed_at=timezone.now())
        elif op == "resubscribe":
            contacts.update(status=Contact.Status.SUBSCRIBED, status_reason="", unsubscribed_at=None)
        elif op == "delete":
            count = contacts.count()
            contacts.delete()
            return Response({"affected": count})
        else:
            return Response({"detail": f"Unknown op '{op}'."}, status=http.HTTP_400_BAD_REQUEST)
        return Response({"affected": contacts.count()})


class ContactListViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = ContactList.objects.all()
    serializer_class = ContactListSerializer


class CampaignSenderViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = CampaignSender.objects.select_related("mailbox").all()
    serializer_class = CampaignSenderSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Send a probe through this route to prove the credentials work."""
        sender = self.get_object()
        to_addr = request.data.get("to") or sender.sender_email
        if not to_addr:
            return Response({"ok": False, "error": "No address to test with."},
                            status=http.HTTP_400_BAD_REQUEST)
        return Response(send_test(sender, to_addr))

    @action(detail=True, methods=["get"])
    def reply_coverage(self, request, pk=None):
        """Which of the workspace's mailboxes this route may carry replies for.

        Surfaces the SPF/DKIM constraint before a send is attempted, rather than
        letting the engine discover it when a mailbox hits its cap.
        """
        from apps.mailboxes.models import Mailbox

        route = self.get_object()
        rows = []
        for mailbox in Mailbox.objects.filter(workspace=self.get_workspace()):
            allowed, reason = route.can_send_as(mailbox.email_address)
            rows.append({
                "mailbox": mailbox.name,
                "email": mailbox.email_address,
                "allowed": allowed,
                "reason": reason,
                "daily_send_limit": mailbox.daily_send_limit,
            })
        return Response({
            "route": route.name,
            "authorized_domains": route.authorized_domain_list,
            "use_for_replies": route.use_for_replies,
            "mailboxes": rows,
        })

    @action(detail=False, methods=["get"])
    def capacity(self, request):
        """Total sends the workspace has left today across all active routes.

        `unlimited` means at least one route has no daily cap, so the number is a
        floor rather than the real ceiling.
        """
        routes = self.get_queryset().filter(is_active=True)
        total, unlimited = 0, False
        for route in routes:
            remaining = route.remaining_today()
            if remaining is None:
                unlimited = True
            else:
                total += remaining
        return Response({"remaining_today": total, "unlimited": unlimited, "routes": routes.count()})


class CampaignViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Campaign.objects.prefetch_related("lists", "senders", "attachments").all()
    serializer_class = CampaignSerializer

    def get_queryset(self):
        """Annotate the report figures so a page of campaigns costs one query.

        Previously the serializer called stats() and audience_size() per row — seven
        queries per campaign, so a workspace with 50 campaigns issued 350 of them
        just to draw the list.

        The two annotations are deliberately NOT combined: `recipients` and
        `lists__contacts` are separate joins, and aggregating both in one query
        multiplies the rows and silently inflates every count.
        """
        qs = super().get_queryset()
        stats = {f"_stat_{name}": expr for name, expr in Campaign.stats_aggregates().items()}
        qs = qs.annotate(**stats)
        return qs

    def get_serializer_context(self):
        """Audience sizes for the whole page in one query, keyed by campaign id."""
        ctx = super().get_serializer_context()
        if getattr(self, "action", None) == "list":
            ids = list(self.filter_queryset(self.get_queryset()).values_list("id", flat=True))
            rows = (
                Campaign.objects.filter(id__in=ids)
                .annotate(n=models.Count(
                    "lists__contacts",
                    filter=models.Q(lists__contacts__status=Contact.Status.SUBSCRIBED),
                    distinct=True,
                ))
                .values_list("id", "n")
            )
            ctx["audience_sizes"] = dict(rows)
        return ctx

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Queue a campaign for sending, now or at `scheduled_for`."""
        campaign = self.get_object()
        if campaign.status in {Campaign.Status.SENDING, Campaign.Status.SENT}:
            return Response({"detail": f"Campaign is already {campaign.status}."},
                            status=http.HTTP_400_BAD_REQUEST)
        if not campaign.senders.filter(is_active=True).exists():
            return Response({"detail": "Add at least one active sending route first."},
                            status=http.HTTP_400_BAD_REQUEST)
        if not campaign.lists.exists():
            return Response({"detail": "Pick at least one contact list."},
                            status=http.HTTP_400_BAD_REQUEST)

        added = materialise(campaign)
        if campaign.scheduled_for and campaign.scheduled_for > timezone.now():
            campaign.status = Campaign.Status.SCHEDULED
        else:
            campaign.status = Campaign.Status.SENDING
            campaign.started_at = campaign.started_at or timezone.now()
        campaign.error = ""
        campaign.save(update_fields=["status", "started_at", "error"])
        return Response({"status": campaign.status, "queued": added, "stats": campaign.stats()})

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in {Campaign.Status.SENDING, Campaign.Status.SCHEDULED}:
            return Response({"detail": "Only a sending or scheduled campaign can be paused."},
                            status=http.HTTP_400_BAD_REQUEST)
        campaign.status = Campaign.Status.PAUSED
        campaign.save(update_fields=["status"])
        return Response({"status": campaign.status})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status != Campaign.Status.PAUSED:
            return Response({"detail": "Campaign is not paused."}, status=http.HTTP_400_BAD_REQUEST)
        campaign.status = Campaign.Status.SENDING
        campaign.save(update_fields=["status"])
        return Response({"status": campaign.status})

    @action(detail=True, methods=["post"])
    def send_now(self, request, pk=None):
        """Push one batch immediately instead of waiting for the next engine tick."""
        campaign = self.get_object()
        if campaign.status != Campaign.Status.SENDING:
            return Response({"detail": "Start the campaign first."}, status=http.HTTP_400_BAD_REQUEST)
        sent = send_campaign_batch(campaign)
        campaign.refresh_from_db()
        return Response({"sent": sent, "status": campaign.status, "stats": campaign.stats()})

    @action(detail=True, methods=["post"])
    def test_send(self, request, pk=None):
        """Send this campaign's rendered content to one address, without tracking it."""
        campaign = self.get_object()
        to_addr = request.data.get("to")
        route = campaign.senders.filter(is_active=True).first()
        if not to_addr:
            return Response({"detail": "Supply an address to send the test to."},
                            status=http.HTTP_400_BAD_REQUEST)
        if route is None:
            return Response({"detail": "Add an active sending route first."},
                            status=http.HTTP_400_BAD_REQUEST)

        from .sending import SendError, deliver

        contact = Contact(email=to_addr, first_name="Test", workspace=campaign.workspace,
                          unsubscribe_token="preview")
        recipient = CampaignRecipient(campaign=campaign, contact=contact, token="preview")
        context = recipient_context(campaign, recipient, route)
        subject = f"[TEST] {campaign.subject}"
        from apps.automation.engine import render_template

        subject = render_template(subject, context, workspace=campaign.workspace)
        # Tracking is stripped for tests: a preview must not inflate the real report.
        body = render_template(campaign.body, context, workspace=campaign.workspace)
        try:
            deliver(route, contact, subject, body, campaign.is_html, [])
        except SendError as exc:
            return Response({"ok": False, "error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return Response({"ok": False, "error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "detail": f"Test sent to {to_addr} via {route.name}"})

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Render the campaign against a sample contact, as the preview modal shows it."""
        campaign = self.get_object()
        route = campaign.senders.filter(is_active=True).first() or CampaignSender(
            name="Preview", workspace=campaign.workspace, from_email="you@your-domain.com"
        )
        contact = (
            Contact.objects.filter(workspace=campaign.workspace, status=Contact.Status.SUBSCRIBED).first()
            or Contact(email="jane.doe@example.com", first_name="Jane", last_name="Doe",
                       company="Example Ltd", workspace=campaign.workspace, unsubscribe_token="preview")
        )
        recipient = CampaignRecipient(campaign=campaign, contact=contact, token="preview")
        context = recipient_context(campaign, recipient, route)
        from apps.automation.engine import render_template

        body, is_html = build_body(campaign, recipient, context)
        return Response({
            "subject": render_template(campaign.subject, context, workspace=campaign.workspace),
            "body": body,
            "is_html": is_html,
            "to": contact.email,
        })

    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        """The per-recipient delivery log, newest activity first."""
        campaign = self.get_object()
        rows = campaign.recipients.select_related("contact", "sender")
        if (state := request.query_params.get("status")):
            rows = rows.filter(status=state)
        return Response(CampaignRecipientSerializer(rows[:500], many=True).data)
