from django.db import models


class Placeholder(models.Model):
    """A reusable template variable, e.g. {{sender_name}} -> resolved at send time.

    `key` is what the user types in a template; `sample` is shown in the UI.
    Some keys are resolved dynamically by the engine (sender_name, original_subject,
    date, mailbox_name); others act as static snippets via `static_value`.
    """

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="placeholders")
    key = models.SlugField(max_length=80, help_text="Used as {{key}} in templates")
    label = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    static_value = models.TextField(blank=True, default="")
    is_dynamic = models.BooleanField(default=False, help_text="Resolved by the engine per message")

    class Meta:
        ordering = ["key"]
        unique_together = [("workspace", "key")]

    def __str__(self):
        return f"{{{{{self.key}}}}}"


class ReplyTemplate(models.Model):
    """A saved reply. Subject/body may contain {{placeholders}}."""

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="templates")
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=255, help_text="e.g. Re: {{original_subject}}")
    body = models.TextField()
    # When on, `body` is an HTML document and is sent as multipart/alternative with a
    # generated plain-text part, so clients that refuse HTML still get readable mail.
    is_html = models.BooleanField(default=False, help_text="Send the body as HTML")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Rule(models.Model):
    """Matches incoming mail by subject and triggers a reply template."""

    class MatchType(models.TextChoices):
        CONTAINS = "contains", "Subject contains"
        EQUALS = "equals", "Subject equals"
        STARTS_WITH = "starts_with", "Subject starts with"
        REGEX = "regex", "Subject matches regex"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    match_type = models.CharField(max_length=20, choices=MatchType.choices, default=MatchType.CONTAINS)
    match_value = models.CharField(max_length=255, help_text="The subject text/pattern to match")
    case_sensitive = models.BooleanField(default=False)

    template = models.ForeignKey(ReplyTemplate, on_delete=models.PROTECT, related_name="rules")
    # Empty = applies to every mailbox; otherwise limited to selected mailboxes.
    mailboxes = models.ManyToManyField("mailboxes.Mailbox", blank=True, related_name="rules")
    # Files attached to every reply this rule sends.
    attachments = models.ManyToManyField("attachments.Attachment", blank=True, related_name="rules")

    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=100, help_text="Lower runs first; first match wins")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return self.name

    def matches(self, subject: str) -> bool:
        import re

        subject = subject or ""
        needle = self.match_value or ""
        if not self.case_sensitive and self.match_type != self.MatchType.REGEX:
            subject_cmp, needle = subject.lower(), needle.lower()
        else:
            subject_cmp = subject

        if self.match_type == self.MatchType.CONTAINS:
            return needle in subject_cmp
        if self.match_type == self.MatchType.EQUALS:
            return subject_cmp.strip() == needle.strip()
        if self.match_type == self.MatchType.STARTS_WITH:
            return subject_cmp.strip().startswith(needle.strip())
        if self.match_type == self.MatchType.REGEX:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return re.search(self.match_value, subject, flags) is not None
            except re.error:
                return False
        return False
