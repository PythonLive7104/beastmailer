"""Bulk email campaigns: audience, sending routes, and per-recipient delivery.

The auto-reply side answers one message at a time; a campaign fans one message out
to thousands. The two share a workspace, the mailboxes, the proxy pool and the
{{placeholder}} renderer — what differs is the pacing, which lives here.

Sending routes
--------------
A campaign draws from a pool of `CampaignSender` rows: each is either one of the
workspace's own mailboxes (good reputation, low daily cap) or an external provider
such as Amazon SES or Mailgun (high cap, needs its own domain warm-up). The engine
round-robins across whichever routes still have quota left today, so a campaign
keeps moving after the mailboxes hit their limits instead of stalling.
"""
import secrets

from django.db import models
from django.utils import timezone

from apps.mailboxes.crypto import decrypt, encrypt


def _token() -> str:
    """Unguessable id for public tracking URLs (open pixel / unsubscribe)."""
    return secrets.token_urlsafe(24)


class Contact(models.Model):
    """One person a campaign can be sent to.

    `email` is unique per workspace: importing the same address twice updates the
    existing contact rather than creating a duplicate that would be mailed twice.
    """

    class Status(models.TextChoices):
        SUBSCRIBED = "subscribed", "Subscribed"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="contacts")
    email = models.EmailField(max_length=320)
    first_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120, blank=True, default="")
    company = models.CharField(max_length=200, blank=True, default="")
    # Free-form imported columns, available to templates as {{contact.<key>}}.
    fields = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SUBSCRIBED)
    # Why they stopped being mailable — a bounce message, or "unsubscribed via link".
    status_reason = models.CharField(max_length=255, blank=True, default="")
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    # Stable per-contact secret for one-click unsubscribe links.
    unsubscribe_token = models.CharField(max_length=64, unique=True, default=_token, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["email"]
        unique_together = [("workspace", "email")]
        indexes = [models.Index(fields=["workspace", "status"])]

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_mailable(self) -> bool:
        """Only subscribed contacts are ever sent to. Bounced and complained
        addresses stay on file (so a re-import can't quietly resurrect them)."""
        return self.status == self.Status.SUBSCRIBED


class ContactList(models.Model):
    """A named audience. A contact may belong to any number of lists."""

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="contact_lists")
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=255, blank=True, default="")
    contacts = models.ManyToManyField(Contact, blank=True, related_name="lists")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def mailable_count(self) -> int:
        return self.contacts.filter(status=Contact.Status.SUBSCRIBED).count()


class CampaignSender(models.Model):
    """One route a campaign can send through: a local mailbox or an external ESP.

    Mailboxes are cheap and already warm but capped low by their provider (Gmail
    cuts off around 500/day). External providers carry the volume. Both are modelled
    here so the engine can rotate over a single mixed pool and simply skip whichever
    routes are out of quota.
    """

    class Kind(models.TextChoices):
        MAILBOX = "mailbox", "Workspace mailbox"
        SMTP = "smtp", "External SMTP relay"
        # SES is driven over its SMTP endpoint rather than the REST API: it needs no
        # SigV4 signing, so the whole app stays free of an AWS SDK dependency.
        SES = "ses", "Amazon SES (SMTP)"
        SENDGRID = "sendgrid", "SendGrid (API)"
        MAILGUN = "mailgun", "Mailgun (API)"
        POSTMARK = "postmark", "Postmark (API)"

    # Providers reached over HTTPS with an API key rather than an SMTP login.
    API_KINDS = {Kind.SENDGRID, Kind.MAILGUN, Kind.POSTMARK}
    # Providers reached over SMTP, whichever credentials they happen to use.
    SMTP_KINDS = {Kind.MAILBOX, Kind.SMTP, Kind.SES}

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="campaign_senders")
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.MAILBOX)

    # kind=mailbox: reuse an account already configured for auto-reply.
    mailbox = models.ForeignKey(
        "mailboxes.Mailbox", null=True, blank=True, on_delete=models.CASCADE, related_name="campaign_senders"
    )

    # Everything below applies to the external kinds only.
    from_email = models.EmailField(max_length=320, blank=True, default="")
    from_name = models.CharField(max_length=160, blank=True, default="")
    # Where replies land. Point this at a mailbox the engine polls and campaign
    # replies flow back into the normal auto-reply pipeline.
    reply_to = models.EmailField(max_length=320, blank=True, default="")

    smtp_host = models.CharField(max_length=200, blank=True, default="")
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)
    username = models.CharField(max_length=320, blank=True, default="")
    secret_encrypted = models.TextField(blank=True, default="")
    # SES needs a region; Mailgun needs the sending domain.
    region = models.CharField(max_length=64, blank=True, default="", help_text="SES region, e.g. eu-west-1")
    domain = models.CharField(max_length=255, blank=True, default="", help_text="Mailgun sending domain")

    # 0 means "no cap we know of" — external providers are usually limited by the
    # plan, not per-day, so the engine treats 0 as unlimited.
    daily_limit = models.PositiveIntegerField(default=0, help_text="Max sends per day. 0 = unlimited.")
    hourly_limit = models.PositiveIntegerField(default=0, help_text="Max sends per hour. 0 = unlimited.")
    # Rotation weight: a route with weight 3 takes three turns to a weight-1 route's
    # one, so a big provider can carry the bulk while mailboxes trickle.
    weight = models.PositiveIntegerField(default=1)
    # Overflow routes sit out until every non-overflow route is capped — this is what
    # makes "use SES only once the mailboxes are exhausted" expressible.
    is_overflow = models.BooleanField(
        default=False, help_text="Only used once the non-overflow routes have hit their caps."
    )
    use_proxy = models.BooleanField(default=False, help_text="Route SMTP through the workspace proxy pool.")
    # Lets the auto-reply engine borrow this route when a mailbox has used up its
    # own daily quota, so replies keep going out after the account is capped.
    # The provider must be authorised to send as the mailbox's domain, or the reply
    # will fail SPF/DKIM — see the note on the Sending routes page.
    use_for_replies = models.BooleanField(
        default=False, help_text="Also use this route for auto-replies once a mailbox hits its daily cap."
    )
    # Domains this provider is actually verified to send for. Blank falls back to the
    # from_email domain, which is the domain you had to verify to configure the route
    # at all. Enforced by can_send_as(): a reply is only handed to a route that is
    # authorised for the mailbox's own domain, because the reply keeps the mailbox's
    # From address and would otherwise fail SPF/DKIM.
    authorized_domains = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated domains this provider may send as. Blank = the From address's domain.",
    )

    class ReplyIdentity(models.TextChoices):
        MAILBOX = "mailbox", "Keep the mailbox's own address"
        ROUTE = "route", "Send as this route, Reply-To the mailbox"

    # How a borrowed auto-reply presents itself.
    #
    # MAILBOX keeps the original From, which reads naturally in the thread but only
    # authenticates for domains this route is verified for.
    #
    # ROUTE sends under the route's own verified address and puts the mailbox in
    # Reply-To. The reply visibly comes from a different address, but it always
    # authenticates — so a free Gmail or Outlook mailbox can still overflow to an
    # external provider instead of being stuck at its daily cap.
    # Defaults to ROUTE: never put an address in From that this provider is not
    # verified for. MAILBOX stays available because it is not forgery when the
    # domain is genuinely yours and verified here — it just has to be opted into.
    reply_identity = models.CharField(
        max_length=10, choices=ReplyIdentity.choices, default=ReplyIdentity.ROUTE,
        help_text="Whose address a borrowed auto-reply is sent under.",
    )
    is_active = models.BooleanField(default=True)

    sent_today = models.PositiveIntegerField(default=0)
    sent_this_hour = models.PositiveIntegerField(default=0)
    day_started = models.DateField(null=True, blank=True)
    hour_started = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_overflow", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    # Credentials never leave the DB in plaintext, matching Mailbox.password.
    @property
    def secret(self) -> str:
        return decrypt(self.secret_encrypted)

    @secret.setter
    def secret(self, value: str):
        self.secret_encrypted = encrypt(value or "")

    @property
    def sender_email(self) -> str:
        """The address this route actually sends as."""
        if self.kind == self.Kind.MAILBOX and self.mailbox:
            return self.mailbox.email_address
        return self.from_email

    def roll_counters(self, now=None):
        """Reset the day/hour counters when their window has moved on.

        Called before every quota check, so a route left idle overnight starts the
        new day at zero without needing a scheduled job.
        """
        now = now or timezone.now()
        today = timezone.localdate(now)
        changed = False
        if self.day_started != today:
            self.day_started, self.sent_today, changed = today, 0, True
        hour = now.replace(minute=0, second=0, microsecond=0)
        if self.hour_started != hour:
            self.hour_started, self.sent_this_hour, changed = hour, 0, True
        if changed:
            self.save(update_fields=["day_started", "sent_today", "hour_started", "sent_this_hour"])

    # Mailbox providers that will never delegate authority to a third-party sender:
    # no ESP can pass SPF/DKIM as an address at one of these, so a fallback route is
    # impossible for them by construction, not merely misconfigured.
    UNDELEGATABLE_DOMAINS = {
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
        "yahoo.com", "ymail.com", "aol.com", "icloud.com", "me.com", "proton.me",
        "protonmail.com", "gmx.com", "mail.com", "yandex.com", "zoho.com",
    }

    @property
    def authorized_domain_list(self) -> list[str]:
        """Domains this route may send as, defaulting to its own From domain."""
        raw = [d.strip().lower().lstrip("@") for d in (self.authorized_domains or "").split(",")]
        explicit = [d for d in raw if d]
        if explicit:
            return explicit
        own = (self.from_email or "").rpartition("@")[2].strip().lower()
        return [own] if own else []

    def can_send_as(self, address: str) -> tuple[bool, str]:
        """Whether this route may send mail whose From is `address`.

        Returns (allowed, reason). The reason is surfaced in the UI and the audit
        log, so a blocked reply explains itself instead of silently not going out.
        """
        # Sending under the route's own verified address forges nothing, so there is
        # nothing to authorise — this is the escape hatch for undelegatable mailboxes.
        if self.reply_identity == self.ReplyIdentity.ROUTE:
            return True, ""
        domain = (address or "").rpartition("@")[2].strip().lower()
        if not domain:
            return False, "No sender domain to check."
        if domain in self.UNDELEGATABLE_DOMAINS:
            return False, (
                f"{domain} never authorises third-party senders, so no provider can send "
                f"as this address. Replies from it must go through the mailbox itself."
            )
        allowed = self.authorized_domain_list
        if not allowed:
            return False, "This route has no authorised sending domain configured."
        # An entry authorises its own subdomains too: verifying example.com in SES
        # covers mail.example.com.
        for candidate in allowed:
            if domain == candidate or domain.endswith(f".{candidate}"):
                return True, ""
        return False, (
            f"This route is authorised for {', '.join(allowed)} — not {domain}. "
            f"Sending as {domain} would fail SPF/DKIM."
        )

    def remaining_today(self) -> int | None:
        """Sends left in the current day, or None when uncapped."""
        if not self.daily_limit:
            return None
        return max(0, self.daily_limit - self.sent_today)

    def has_quota(self, now=None) -> bool:
        self.roll_counters(now)
        if self.daily_limit and self.sent_today >= self.daily_limit:
            return False
        if self.hourly_limit and self.sent_this_hour >= self.hourly_limit:
            return False
        return True

    def record_send(self):
        self.sent_today += 1
        self.sent_this_hour += 1
        self.save(update_fields=["sent_today", "sent_this_hour"])


class Campaign(models.Model):
    """One bulk send: a message, an audience, and the routes to send it through."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        SENDING = "sending", "Sending"
        PAUSED = "paused", "Paused"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=998)
    body = models.TextField(blank=True, default="")
    is_html = models.BooleanField(default=True)
    preheader = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Preview text shown after the subject in most inboxes.",
    )

    lists = models.ManyToManyField(ContactList, blank=True, related_name="campaigns")
    senders = models.ManyToManyField(CampaignSender, blank=True, related_name="campaigns")
    attachments = models.ManyToManyField("attachments.Attachment", blank=True, related_name="campaigns")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    # Pace the whole campaign independently of the per-route caps: useful for a slow
    # drip that looks less like a blast.
    per_tick_limit = models.PositiveIntegerField(
        default=25, help_text="Most emails to send per engine tick, across all routes."
    )
    track_opens = models.BooleanField(default=True)
    track_clicks = models.BooleanField(default=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def stats(self) -> dict:
        """Counts for the campaign report, in one query per bucket."""
        rows = self.recipients.values("status").annotate(n=models.Count("id"))
        by_status = {r["status"]: r["n"] for r in rows}
        total = sum(by_status.values())
        sent = self.recipients.filter(
            status__in=[CampaignRecipient.Status.SENT, CampaignRecipient.Status.OPENED,
                        CampaignRecipient.Status.CLICKED]
        ).count()
        return {
            "total": total,
            "pending": by_status.get(CampaignRecipient.Status.PENDING, 0),
            "sent": sent,
            "opened": self.recipients.filter(opened_at__isnull=False).count(),
            "clicked": self.recipients.filter(clicked_at__isnull=False).count(),
            "unsubscribed": self.recipients.filter(unsubscribed_at__isnull=False).count(),
            "bounced": by_status.get(CampaignRecipient.Status.BOUNCED, 0),
            "failed": by_status.get(CampaignRecipient.Status.FAILED, 0),
            "skipped": by_status.get(CampaignRecipient.Status.SKIPPED, 0),
        }


class CampaignRecipient(models.Model):
    """One contact's copy of one campaign — the unit the engine actually sends.

    Materialised up front when the campaign starts, so pausing, resuming and
    reporting all work off the same rows, and a contact can never be sent the same
    campaign twice.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        OPENED = "opened", "Opened"
        CLICKED = "clicked", "Clicked"
        BOUNCED = "bounced", "Bounced"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="campaign_recipients")
    sender = models.ForeignKey(
        CampaignSender, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipients"
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Per-recipient secret: what the open pixel and click links carry, so tracking
    # can attribute a hit without exposing the contact's address in the URL.
    token = models.CharField(max_length=64, unique=True, default=_token, db_index=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    open_count = models.PositiveIntegerField(default=0)
    clicked_at = models.DateTimeField(null=True, blank=True)
    click_count = models.PositiveIntegerField(default=0)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    attempt_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        unique_together = [("campaign", "contact")]
        indexes = [models.Index(fields=["campaign", "status"])]

    def __str__(self):
        return f"{self.campaign.name} -> {self.contact.email}"
