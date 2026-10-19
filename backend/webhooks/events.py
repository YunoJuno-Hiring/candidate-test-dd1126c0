"""Event emission: writes outbox rows for the `deliver_webhooks` worker.

Call `emit_event` inside the same transaction as the state change, so the
deliveries commit (or roll back) together with it.
"""
import uuid

from django.utils import timezone

from .models import WebhookDelivery, WebhookEndpoint

PAYLOAD_VERSION = 1

TIMESHEET_SUBMITTED = 'timesheet.submitted'
WEBHOOK_TEST = 'webhook.test'


def build_payload(event_type, data, event_id=None, created_at=None):
    event_id = event_id or uuid.uuid4()
    created_at = created_at or timezone.now()
    return {
        'id': f'evt_{event_id.hex}',
        'type': event_type,
        'version': PAYLOAD_VERSION,
        'created_at': created_at.isoformat(),
        'data': data,
    }


def _create_delivery(endpoint, event_id, event_type, payload, next_attempt_at=None):
    return WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        next_attempt_at=next_attempt_at or timezone.now(),
    )


def emit_event(company, event_type, data):
    """Queue one delivery per active endpoint of `company`. Returns the deliveries."""
    endpoints = list(WebhookEndpoint.objects.filter(company=company, active=True))
    if not endpoints:
        return []
    event_id = uuid.uuid4()
    payload = build_payload(event_type, data, event_id=event_id)
    return [_create_delivery(endpoint, event_id, event_type, payload) for endpoint in endpoints]


def create_test_delivery(endpoint, next_attempt_at=None):
    """Queue a `webhook.test` event for a single endpoint."""
    event_id = uuid.uuid4()
    payload = build_payload(
        WEBHOOK_TEST,
        {'endpoint_id': endpoint.id, 'message': 'Test event from YunoJuno.'},
        event_id=event_id,
    )
    return _create_delivery(endpoint, event_id, WEBHOOK_TEST, payload, next_attempt_at)


def timesheet_entry_data(entry):
    return {
        'timesheet_entry': {
            'id': entry.id,
            'contract_id': entry.contract_id,
            'freelancer_id': entry.contract.freelancer_id,
            'date': entry.date.isoformat(),
            'hours': f'{entry.hours:.2f}',
            'status': entry.status,
        }
    }


def emit_timesheet_submitted(entry):
    return emit_event(entry.contract.company, TIMESHEET_SUBMITTED, timesheet_entry_data(entry))
