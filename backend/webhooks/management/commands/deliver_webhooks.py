"""
Webhook delivery worker.

Polls the outbox for due deliveries, sends them, and schedules retries.
Several workers can run at once: rows are claimed with
SELECT ... FOR UPDATE SKIP LOCKED.

  python manage.py deliver_webhooks            # run until interrupted
  python manage.py deliver_webhooks --once     # one pass, then exit (cron / tests)
"""
import time

from django.core.management.base import BaseCommand

from webhooks.delivery import process_due_deliveries


class Command(BaseCommand):
    help = 'Send due outbound webhook deliveries and schedule retries.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process one batch and exit.')
        parser.add_argument('--interval', type=float, default=2.0, help='Seconds to sleep between polls.')
        parser.add_argument('--batch-size', type=int, default=50, help='Max deliveries per poll.')

    def handle(self, *args, once=False, interval=2.0, batch_size=50, **options):
        self.stdout.write('Webhook worker started.')
        try:
            while True:
                attempted = process_due_deliveries(limit=batch_size)
                if attempted:
                    self.stdout.write(f'Attempted {attempted} deliveries.')
                if once:
                    break
                # Only sleep when idle, so a backlog drains at full speed.
                if attempted < batch_size:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('Webhook worker stopped.')
