"""Seed the database with demo data (owned by the admin user)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.automation.models import Config
from apps.mail.models import EmailMessage, normalize_subject
from apps.mailboxes.models import Mailbox
from apps.rules.models import Placeholder, ReplyTemplate, Rule
from apps.workspaces.services import ensure_personal_workspace


class Command(BaseCommand):
    help = "Create a demo admin + workspace with mailboxes, rules, placeholders and activity."

    def handle(self, *args, **options):
        User = get_user_model()
        admin, created = User.objects.get_or_create(
            username="admin", defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin.set_password("admin12345")
            admin.save()
            self.stdout.write(self.style.SUCCESS("Created superuser admin / admin12345"))

        ws = ensure_personal_workspace(admin)
        Config.load(ws)

        for key, label, desc, dynamic in [
            ("sender_name", "Sender name", "Name derived from the incoming address", True),
            ("sender_email", "Sender email", "The incoming from address", True),
            ("original_subject", "Original subject", "Subject of the received email", True),
            ("mailbox_name", "Mailbox name", "Name of the receiving mailbox", True),
            ("date", "Today's date", "Current date, formatted", True),
            ("company", "Company name", "Your company name", False),
        ]:
            Placeholder.objects.get_or_create(
                workspace=ws, key=key,
                defaults={"label": label, "description": desc, "is_dynamic": dynamic,
                          "static_value": "Acme Ltd." if key == "company" else ""},
            )

        mb1, _ = Mailbox.objects.get_or_create(
            workspace=ws, email_address="sales@usconstructiongroups.com",
            defaults=dict(
                name="Sales inbox", imap_host="imap.example.com", smtp_host="smtp.example.com",
                username="sales@usconstructiongroups.com", is_active=True,
            ),
        )
        mb2, _ = Mailbox.objects.get_or_create(
            workspace=ws, email_address="projects@usconstructiongroups.com",
            defaults=dict(
                name="Projects inbox", imap_host="imap.example.com", smtp_host="smtp.example.com",
                username="projects@usconstructiongroups.com", is_active=True,
            ),
        )

        tpl, _ = ReplyTemplate.objects.get_or_create(
            workspace=ws, name="Project inquiry auto-reply",
            defaults=dict(
                subject="Re: {{original_subject}}",
                body=("Hi {{sender_name}},\n\nThanks for reaching out about your project. "
                      "We've received your message on {{date}} and a specialist will follow up "
                      "shortly.\n\nBest regards,\n{{company}}"),
            ),
        )
        Rule.objects.get_or_create(
            workspace=ws, name="Project inquiries",
            defaults=dict(match_type=Rule.MatchType.CONTAINS, match_value="Project Inquiry",
                          template=tpl),
        )

        if EmailMessage.objects.filter(workspace=ws).count() == 0:
            now = timezone.now()
            samples = [
                (mb1, EmailMessage.Direction.OUTGOING, EmailMessage.Status.SENT,
                 "Re: Project Inquiry: Ref Z3aapoBM", "matt.mcdaniel@usconstructiongroups.com"),
                (mb1, EmailMessage.Direction.INCOMING, EmailMessage.Status.RECEIVED,
                 "Grow Your Business with Outdoor Lighting", "jessica.brooks@gardenlightled.com"),
                (mb2, EmailMessage.Direction.OUTGOING, EmailMessage.Status.SCHEDULED,
                 "Re: Grow Your Business with Outdoor Lighting", "jessica.brooks@gardenlightled.com"),
                (mb1, EmailMessage.Direction.OUTGOING, EmailMessage.Status.SENT,
                 "Re: Project Inquiry: Ref 2hpUhPIF", "matt.mcdaniel@usconstructiongroups.com"),
            ]
            for i, (mb, direction, status, subject, addr) in enumerate(samples):
                incoming = direction == EmailMessage.Direction.INCOMING
                EmailMessage.objects.create(
                    workspace=ws, mailbox=mb, direction=direction, status=status, subject=subject,
                    thread_key=normalize_subject(subject),
                    from_addr=addr if incoming else mb.email_address,
                    to_addr=mb.email_address if incoming else addr,
                    received_at=now - timedelta(minutes=30 - i) if incoming else None,
                    sent_at=now - timedelta(minutes=28 - i) if status == "sent" else None,
                    scheduled_for=now + timedelta(minutes=15) if status == "scheduled" else None,
                )

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
