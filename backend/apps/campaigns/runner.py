"""Campaign execution: materialise the audience, then drip it out per engine tick.

Called from the same `run_once()` tick as the auto-reply sender, so campaigns need
no second process — the existing `run_engine` command drives both.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.billing.services import workspace_can_send
from apps.notifications.telegram import notify
from apps.security.models import SystemEvent

from .models import Campaign, CampaignRecipient, CampaignSender, Contact
from .sending import SendError, build_body, deliver, recipient_context

# A recipient that fails transiently is retried on later ticks up to this many times.
MAX_ATTEMPTS = 3


def materialise(campaign: Campaign) -> int:
    """Create the pending recipient rows for a campaign's audience.

    Idempotent: `unique_together (campaign, contact)` means a contact on two of the
    campaign's lists still gets exactly one copy, and re-running after a pause adds
    only contacts that joined a list since.
    """
    contacts = (
        Contact.objects.filter(
            lists__in=campaign.lists.all(),
            status=Contact.Status.SUBSCRIBED,
        )
        .distinct()
    )
    existing = set(campaign.recipients.values_list("contact_id", flat=True))
    fresh = [
        CampaignRecipient(campaign=campaign, contact=contact)
        for contact in contacts
        if contact.id not in existing
    ]
    if fresh:
        CampaignRecipient.objects.bulk_create(fresh, batch_size=500)
    return len(fresh)


def eligible_routes(campaign: Campaign, now=None) -> list[CampaignSender]:
    """Routes with quota left, overflow held back until the others are exhausted."""
    routes = [s for s in campaign.senders.filter(is_active=True) if s.has_quota(now)]
    primary = [s for s in routes if not s.is_overflow]
    return primary or [s for s in routes if s.is_overflow]


def pick_route(routes: list[CampaignSender]) -> CampaignSender | None:
    """Weighted least-used: the route furthest below its share of today's volume.

    Dividing by weight means a weight-5 provider absorbs five sends for every one a
    weight-1 mailbox takes, without needing to track whose turn it is between ticks.
    """
    if not routes:
        return None
    return min(routes, key=lambda s: s.sent_today / max(1, s.weight))


def _finish_if_done(campaign: Campaign) -> bool:
    if campaign.recipients.filter(status=CampaignRecipient.Status.PENDING).exists():
        return False
    campaign.status = Campaign.Status.SENT
    campaign.finished_at = timezone.now()
    campaign.save(update_fields=["status", "finished_at"])
    stats = campaign.stats()
    notify(campaign.workspace, "sent",
           f"📣 <b>Campaign finished</b>: {campaign.name}\n"
           f"{stats['sent']} sent · {stats['failed']} failed · {stats['skipped']} skipped")
    SystemEvent.log("campaign", f"Campaign '{campaign.name}' finished: {stats}",
                    workspace=campaign.workspace)
    return True


def send_campaign_batch(campaign: Campaign, limit: int | None = None) -> int:
    """Send up to `limit` of this campaign's pending recipients. Returns how many went."""
    limit = limit or campaign.per_tick_limit
    sent = 0

    pending = (
        campaign.recipients.filter(status=CampaignRecipient.Status.PENDING)
        .select_related("contact")
        .order_by("id")
    )
    attachments = list(campaign.attachments.all())

    for recipient in pending[: limit * 2]:  # headroom: some rows get skipped, not sent
        if sent >= limit:
            break

        # The contact may have unsubscribed or bounced since the audience was built.
        if not recipient.contact.is_mailable:
            recipient.status = CampaignRecipient.Status.SKIPPED
            recipient.error = f"Contact is {recipient.contact.status}"
            recipient.save(update_fields=["status", "error"])
            continue

        routes = eligible_routes(campaign)
        if not routes:
            # Every route is out of quota — stop here and pick up on a later tick,
            # which is exactly what the daily caps are meant to cause.
            break
        route = pick_route(routes)

        try:
            context = recipient_context(campaign, recipient, route)
            subject = _render_subject(campaign, context)
            body, is_html = build_body(campaign, recipient, context)
            deliver(route, recipient.contact, subject, body, is_html, attachments)
        except SendError as exc:
            _record_failure(recipient, route, exc, permanent=exc.permanent)
            continue
        except Exception as exc:  # noqa: BLE001 - one bad recipient must not stop the run
            _record_failure(recipient, route, exc, permanent=False)
            continue

        recipient.status = CampaignRecipient.Status.SENT
        recipient.sender = route
        recipient.sent_at = timezone.now()
        recipient.error = ""
        recipient.save(update_fields=["status", "sender", "sent_at", "error"])
        route.record_send()
        sent += 1

    _finish_if_done(campaign)
    return sent


def _render_subject(campaign: Campaign, context: dict) -> str:
    from apps.automation.engine import render_template

    return render_template(campaign.subject, context, workspace=campaign.workspace)


def _record_failure(recipient: CampaignRecipient, route, exc, permanent: bool):
    recipient.attempt_count += 1
    recipient.error = str(exc)[:2000]
    recipient.sender = route
    if permanent or recipient.attempt_count >= MAX_ATTEMPTS:
        recipient.status = CampaignRecipient.Status.FAILED
        # A hard rejection is the address's fault, not the route's: mark the contact
        # bounced so no future campaign wastes reputation on it again.
        if permanent:
            recipient.status = CampaignRecipient.Status.BOUNCED
            Contact.objects.filter(pk=recipient.contact_id).update(
                status=Contact.Status.BOUNCED, status_reason=str(exc)[:255]
            )
    recipient.save(update_fields=["status", "attempt_count", "error", "sender"])
    if route is not None:
        CampaignSender.objects.filter(pk=route.pk).update(last_error=str(exc)[:2000])


def run_campaigns(workspace=None) -> int:
    """One tick of campaign sending across every running campaign. Returns emails sent.

    Scheduled campaigns whose time has come are started here, so "schedule for 9am"
    needs nothing but the engine already running.
    """
    now = timezone.now()
    due = Campaign.objects.filter(
        Q(status=Campaign.Status.SENDING)
        | Q(status=Campaign.Status.SCHEDULED, scheduled_for__lte=now)
    )
    if workspace is not None:
        due = due.filter(workspace=workspace)

    total = 0
    for campaign in due.select_related("workspace"):
        # Paywall, same rule as auto-replies: a lapsed subscription pauses sending
        # without losing the queue.
        if not workspace_can_send(campaign.workspace):
            continue

        if campaign.status == Campaign.Status.SCHEDULED:
            campaign.status = Campaign.Status.SENDING
            campaign.started_at = now
            campaign.save(update_fields=["status", "started_at"])
            materialise(campaign)
            SystemEvent.log("campaign", f"Campaign '{campaign.name}' started", workspace=campaign.workspace)
            notify(campaign.workspace, "sent", f"📣 <b>Campaign started</b>: {campaign.name}")

        try:
            total += send_campaign_batch(campaign)
        except Exception as exc:  # noqa: BLE001 - keep other campaigns running
            campaign.status = Campaign.Status.FAILED
            campaign.error = str(exc)[:2000]
            campaign.save(update_fields=["status", "error"])
            SystemEvent.log("campaign", f"Campaign '{campaign.name}' failed: {exc}",
                            level="error", workspace=campaign.workspace)
    return total
