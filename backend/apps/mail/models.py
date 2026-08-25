import re

from django.db import models


def normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes and collapse whitespace to build a thread key.

    Two emails with the same normalized subject are treated as one thread, which
    is how replies get matched back to the original sent email.
    """
    subject = (subject or "").strip()
    prev = None
    while prev != subject:
        prev = subject
        subject = re.sub(r"^\s*(re|fwd?|aw|sv)\s*(\[\d+\])?\s*:\s*", "", subject, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", subject).strip().lower()


class EmailMessage(models.Model):
    """A single email the app has sent or received. Powers the activity feed."""

    class Direction(models.TextChoices):
        INCOMING = "incoming", "Incoming"
        OUTGOING = "outgoing", "Outgoing"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        SCHEDULED = "scheduled", "Scheduled"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="messages")
    mailbox = models.ForeignKey(
        "mailboxes.Mailbox", on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=12, choices=Status.choices)

    message_id = models.CharField(max_length=512, blank=True, default="", db_index=True)
    in_reply_to = models.CharField(max_length=512, blank=True, default="")
    imap_uid = models.PositiveBigIntegerField(null=True, blank=True)
    # Which IMAP folder an incoming message was found in ("INBOX", "[Gmail]/Spam", ...).
    # UIDs repeat across folders, so this is what makes imap_uid unambiguous.
    folder = models.CharField(max_length=255, blank=True, default="")

    subject = models.CharField(max_length=998, blank=True, default="")
    thread_key = models.CharField(max_length=998, blank=True, default="", db_index=True)
    from_addr = models.CharField(max_length=320, blank=True, default="")
    # The display name from the incoming "From:" header (e.g. "Jane Doe"), when present.
    from_name = models.CharField(max_length=255, blank=True, default="")
    to_addr = models.CharField(max_length=998, blank=True, default="")
    body = models.TextField(blank=True, default="")
    # Copied from the template at scheduling time: the template may be edited or
    # deleted before the delay elapses, so the reply carries its own format.
    is_html = models.BooleanField(default=False)

    # Set for auto-replies: which rule fired and the reply it is/was answering.
    matched_rule = models.ForeignKey(
        "rules.Rule", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )
    reply_to_message = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )
    attachments = models.ManyToManyField(
        "attachments.Attachment", blank=True, related_name="messages"
    )

    scheduled_for = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    # Send-retry bookkeeping: how many send attempts a reply has had, and the
    # earliest time to try again after a transient failure.
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["direction", "status"])]

    def __str__(self):
        return f"[{self.status}] {self.subject}"

    def save(self, *args, **kwargs):
        if self.subject and not self.thread_key:
            self.thread_key = normalize_subject(self.subject)
        # Workspace always follows the mailbox it belongs to.
        if self.mailbox_id and not self.workspace_id:
            self.workspace_id = self.mailbox.workspace_id
        super().save(*args, **kwargs)
