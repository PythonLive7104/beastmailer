"""Run the mail automation engine on a loop.

Usage:
    python manage.py run_engine            # loop forever, using the configured poll interval
    python manage.py run_engine --once     # single tick then exit (good for cron)
"""
import time

from django.core.management.base import BaseCommand
from django.db.models import Min

from apps.automation.engine import run_once
from apps.automation.models import Config


class Command(BaseCommand):
    help = "Poll mailboxes for new mail and send due auto-replies."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run a single tick and exit.")

    def handle(self, *args, **options):
        run_forever = not options["once"]
        while True:
            stats = run_once()
            self.stdout.write(
                self.style.SUCCESS(
                    f"tick: polled={stats['polled']} ingested={stats['ingested']} "
                    f"sent={stats['sent']} errors={len(stats['errors'])}"
                )
            )
            for err in stats["errors"]:
                self.stderr.write(self.style.WARNING(f"  {err}"))
            if not run_forever:
                break
            # Tick at the shortest poll interval configured across all workspaces.
            interval = Config.objects.aggregate(m=Min("poll_interval_seconds"))["m"] or 30
            time.sleep(max(5, interval))
