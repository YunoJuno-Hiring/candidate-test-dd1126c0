"""Outbound delivery: signs and POSTs queued deliveries, records attempts, schedules retries.

Run by the `deliver_webhooks` management command. Only the "send test event"
action calls `attempt_delivery` from a request, so the admin gets immediate
feedback; real events are always sent by the worker.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

from django.db import transaction
from django.utils import timezone

from .events import create_test_delivery
from .models import WebhookDelivery, WebhookDeliveryAttempt, WebhookEndpoint
from .signing import signature_header

logger = logging.getLogger(__name__)

# Wait after attempt N fails before attempt N+1. Six attempts in total,
# spread over ~8.6 hours, then the delivery is marked failed.
RETRY_DELAYS = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
]
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1

TIMEOUT_SECONDS = 5
# A claimed row is hidden from other workers for this long. Must exceed the
# HTTP timeout; if a worker dies mid-send, the row becomes due again after it.
CLAIM_LEASE = timedelta(seconds=60)
RESPONSE_BODY_LIMIT = 1024
USER_AGENT = 'YunoJuno-Webhooks/1'


@dataclass
class SendResult:
    status: Optional[int]  # None when no HTTP response was received
    body: str = ''
    error: str = ''

    @property
    def ok(self):
        return self.status is not None and 200 <= self.status < 300


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect is reported as a failed attempt rather than followed: following
    # it would turn the POST into a GET and could send the payload elsewhere.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _read_body(response):
    return response.read(RESPONSE_BODY_LIMIT).decode('utf-8', errors='replace')


def http_post(url: str, body: bytes, headers: dict, timeout: float) -> SendResult:
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with _opener.open(request, timeout=timeout) as response:
            return SendResult(status=response.status, body=_read_body(response))
    except urllib.error.HTTPError as exc:
        return SendResult(status=exc.code, body=_read_body(exc))
    except urllib.error.URLError as exc:
        return SendResult(status=None, error=f'Connection error: {exc.reason}')
    except TimeoutError:
        return SendResult(status=None, error=f'Timed out after {timeout}s')
    except Exception as exc:  # never let one bad endpoint crash the worker
        return SendResult(status=None, error=f'{type(exc).__name__}: {exc}')


Sender = Callable[[str, bytes, dict, float], SendResult]


def encode_payload(payload) -> bytes:
    return json.dumps(payload, separators=(',', ':')).encode()


def build_headers(delivery, attempt_number: int, body: bytes, timestamp: int) -> dict:
    return {
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
        'YJ-Webhook-Id': delivery.payload['id'],
        'YJ-Webhook-Event': delivery.event_type,
        'YJ-Webhook-Attempt': str(attempt_number),
        'YJ-Webhook-Signature': signature_header(delivery.endpoint.secret, timestamp, body),
    }


def attempt_delivery(delivery: WebhookDelivery, sender: Optional[Sender] = None) -> WebhookDelivery:
    """Make one HTTP attempt for a pending delivery and record the outcome."""
    sender = sender or http_post
    if delivery.status != WebhookDelivery.STATUS_PENDING:
        return delivery

    endpoint = delivery.endpoint
    try:
        # Re-read so a disable, URL change or delete made after this row was
        # loaded is respected.
        endpoint.refresh_from_db(fields=['url', 'secret', 'active'])
    except WebhookEndpoint.DoesNotExist:
        return delivery  # deleted; its deliveries were cascade-deleted with it
    if not endpoint.active:
        # Disabled after the event was queued: stop without calling out.
        delivery.status = WebhookDelivery.STATUS_CANCELLED
        delivery.next_attempt_at = None
        delivery.save(update_fields=['status', 'next_attempt_at', 'updated_at'])
        return delivery

    attempt_number = delivery.attempt_count + 1
    body = encode_payload(delivery.payload)
    headers = build_headers(delivery, attempt_number, body, int(time.time()))

    started = time.monotonic()
    result = sender(endpoint.url, body, headers, TIMEOUT_SECONDS)
    duration_ms = int((time.monotonic() - started) * 1000)

    with transaction.atomic():
        WebhookDeliveryAttempt.objects.create(
            delivery=delivery,
            attempt_number=attempt_number,
            response_status=result.status,
            response_body=result.body[:RESPONSE_BODY_LIMIT],
            error=result.error,
            duration_ms=duration_ms,
        )
        delivery.attempt_count = attempt_number
        delivery.last_response_code = result.status
        if result.ok:
            delivery.status = WebhookDelivery.STATUS_SUCCEEDED
            delivery.next_attempt_at = None
        elif attempt_number >= MAX_ATTEMPTS:
            delivery.status = WebhookDelivery.STATUS_FAILED
            delivery.next_attempt_at = None
        else:
            delivery.next_attempt_at = timezone.now() + RETRY_DELAYS[attempt_number - 1]
        delivery.save()
    return delivery


def claim_due_deliveries(limit: int) -> list[int]:
    """Lease up to `limit` due deliveries so concurrent workers skip them."""
    now = timezone.now()
    with transaction.atomic():
        ids = list(
            WebhookDelivery.objects.select_for_update(skip_locked=True)
            .filter(status=WebhookDelivery.STATUS_PENDING, next_attempt_at__lte=now)
            .order_by('next_attempt_at')
            .values_list('id', flat=True)[:limit]
        )
        WebhookDelivery.objects.filter(id__in=ids).update(next_attempt_at=now + CLAIM_LEASE)
    return ids


def process_due_deliveries(limit: int = 50, sender: Optional[Sender] = None) -> int:
    """Attempt up to `limit` due deliveries once each. Returns how many were attempted.

    Rows are claimed one at a time, so each lease only has to cover a single
    send; claiming a whole batch up front would let leases on later rows
    expire while earlier sends are slow, and another worker could send them too.
    """
    attempted = 0
    while attempted < limit:
        ids = claim_due_deliveries(limit=1)
        if not ids:
            break
        attempted += 1
        delivery = WebhookDelivery.objects.select_related('endpoint').filter(id=ids[0]).first()
        if delivery is None:
            continue  # endpoint deleted after the claim
        try:
            attempt_delivery(delivery, sender=sender)
        except Exception:
            # One bad delivery must not stop the worker. The row keeps its lease
            # and is picked up again once the lease expires.
            logger.exception('Unexpected error delivering webhook %s; it will be retried.', delivery.id)
    return attempted


def send_test_event(endpoint, sender: Optional[Sender] = None) -> WebhookDelivery:
    """Queue a webhook.test delivery and make its first attempt inline.

    The row starts leased, so the worker does not pick it up while this
    request is sending; if the request dies, the worker retries it later.
    """
    delivery = create_test_delivery(endpoint, next_attempt_at=timezone.now() + CLAIM_LEASE)
    return attempt_delivery(delivery, sender=sender)
