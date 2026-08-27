"""Run the mail automation engine on a loop.

Usage:
    python manage.py run_engine            # loop forever, using the configured poll interval
    python manage.py run_engine --once     # single tick then exit (good for cron)
"""
import time

from django.core.management.base import BaseCommand

from apps.automation.engine import next_tick_seconds, run_once


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
                    f"tick: polled={stats['polled']} skipped={stats['skipped']} "
                    f"ingested={stats['ingested']} sent={stats['sent']} "
                    f"campaign_sent={stats.get('campaign_sent', 0)} "
                    f"errors={len(stats['errors'])}"
                )
            )
            for err in stats["errors"]:
                self.stderr.write(self.style.WARNING(f"  {err}"))
            if not run_forever:
                break
            # Tick at the shortest cadence any active mailbox asks for; mailboxes on
            # slower intervals are skipped until they come due.
            time.sleep(next_tick_seconds())
