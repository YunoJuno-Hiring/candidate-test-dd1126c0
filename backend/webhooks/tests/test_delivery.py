import hashlib
import hmac
import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.core.management import call_command
from django.utils import timezone

from webhooks import delivery as delivery_module
from webhooks.delivery import (
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    SendResult,
    attempt_delivery,
    http_post,
    process_due_deliveries,
)
from webhooks.events import emit_event
from webhooks.models import WebhookDelivery, WebhookEndpoint
from webhooks.signing import compute_signature, signature_header


class FakeSender:
    """Records every call and replies with queued results (the last one repeats)."""

    def __init__(self, *results):
        self.results = list(results) or [SendResult(status=200, body='ok')]
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({'url': url, 'body': body, 'headers': headers, 'timeout': timeout})
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


@pytest.fixture
def endpoint(northstar):
    return WebhookEndpoint.objects.create(company=northstar, url='https://hooks.northstar.test/yj')


@pytest.fixture
def queued(endpoint):
    [delivery] = emit_event(endpoint.company, 'timesheet.submitted', {'timesheet_entry': {'id': 1}})
    return delivery


# --- Signing ---

def test_signature_matches_hmac_sha256_over_timestamp_and_body():
    body = b'{"id":"evt_1"}'
    expected = hmac.new(b'whsec_test', b'1700000000.' + body, hashlib.sha256).hexdigest()

    assert compute_signature('whsec_test', 1700000000, body) == expected
    assert signature_header('whsec_test', 1700000000, body) == f't=1700000000,v1={expected}'


@pytest.mark.django_db
def test_request_is_signed_with_headers_receivers_can_verify(queued, endpoint):
    sender = FakeSender()

    attempt_delivery(queued, sender=sender)

    call = sender.calls[0]
    headers = call['headers']
    assert call['url'] == endpoint.url
    assert call['timeout'] == 5
    assert json.loads(call['body']) == queued.payload
    assert headers['Content-Type'] == 'application/json'
    assert headers['YJ-Webhook-Id'] == queued.payload['id']
    assert headers['YJ-Webhook-Event'] == 'timesheet.submitted'
    assert headers['YJ-Webhook-Attempt'] == '1'
    timestamp, signature = (part.split('=', 1)[1] for part in headers['YJ-Webhook-Signature'].split(','))
    assert signature == compute_signature(endpoint.secret, int(timestamp), call['body'])


# --- Outcomes ---

@pytest.mark.django_db
def test_2xx_marks_delivery_succeeded_and_logs_attempt(queued):
    attempt_delivery(queued, sender=FakeSender(SendResult(status=204)))

    queued.refresh_from_db()
    assert queued.status == WebhookDelivery.STATUS_SUCCEEDED
    assert queued.attempt_count == 1
    assert queued.last_response_code == 204
    assert queued.next_attempt_at is None
    attempt = queued.attempts.get()
    assert attempt.attempt_number == 1
    assert attempt.response_status == 204
    assert attempt.error == ''


@pytest.mark.django_db
def test_5xx_schedules_first_retry_after_one_minute(queued):
    before = timezone.now()
    attempt_delivery(queued, sender=FakeSender(SendResult(status=500, body='boom')))
    after = timezone.now()

    queued.refresh_from_db()
    assert queued.status == WebhookDelivery.STATUS_PENDING
    assert queued.attempt_count == 1
    assert queued.last_response_code == 500
    assert before + timedelta(minutes=1) <= queued.next_attempt_at <= after + timedelta(minutes=1)
    assert queued.attempts.get().response_body == 'boom'


@pytest.mark.django_db
def test_connection_error_is_logged_without_status_and_retried(queued):
    attempt_delivery(queued, sender=FakeSender(SendResult(status=None, error='Connection error: refused')))

    queued.refresh_from_db()
    assert queued.status == WebhookDelivery.STATUS_PENDING
    assert queued.last_response_code is None
    attempt = queued.attempts.get()
    assert attempt.response_status is None
    assert attempt.error == 'Connection error: refused'


@pytest.mark.django_db
def test_backoff_follows_schedule_then_gives_up(queued):
    sender = FakeSender(SendResult(status=503))

    for attempt_number in range(1, MAX_ATTEMPTS + 1):
        before = timezone.now()
        attempt_delivery(queued, sender=sender)
        queued.refresh_from_db()
        if attempt_number < MAX_ATTEMPTS:
            assert queued.status == WebhookDelivery.STATUS_PENDING
            assert queued.next_attempt_at >= before + RETRY_DELAYS[attempt_number - 1]

    assert MAX_ATTEMPTS == 6
    assert queued.status == WebhookDelivery.STATUS_FAILED
    assert queued.next_attempt_at is None
    assert list(queued.attempts.values_list('attempt_number', flat=True)) == [1, 2, 3, 4, 5, 6]
    assert [c['headers']['YJ-Webhook-Attempt'] for c in sender.calls] == ['1', '2', '3', '4', '5', '6']
    # The event id never changes across retries, so the receiver can dedupe.
    assert {c['headers']['YJ-Webhook-Id'] for c in sender.calls} == {queued.payload['id']}

    # A failed delivery is final: no further attempts.
    attempt_delivery(queued, sender=sender)
    assert len(sender.calls) == MAX_ATTEMPTS


@pytest.mark.django_db
def test_disabled_endpoint_cancels_without_calling_out(queued, endpoint):
    endpoint.active = False
    endpoint.save()
    sender = FakeSender()

    attempt_delivery(queued, sender=sender)

    queued.refresh_from_db()
    assert queued.status == WebhookDelivery.STATUS_CANCELLED
    assert sender.calls == []
    assert queued.attempts.count() == 0


# --- Worker ---

@pytest.mark.django_db
def test_worker_sends_only_due_pending_deliveries(endpoint, queued):
    later = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='timesheet.submitted', payload={'id': 'evt_later'},
        next_attempt_at=timezone.now() + timedelta(minutes=5),
    )
    done = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='timesheet.submitted', payload={'id': 'evt_done'},
        status=WebhookDelivery.STATUS_SUCCEEDED, next_attempt_at=None,
    )
    sender = FakeSender()

    attempted = process_due_deliveries(sender=sender)

    assert attempted == 1
    assert [c['headers']['YJ-Webhook-Id'] for c in sender.calls] == [queued.payload['id']]
    later.refresh_from_db()
    done.refresh_from_db()
    assert later.attempt_count == 0
    assert done.attempt_count == 0


@pytest.mark.django_db
def test_claimed_rows_are_leased_so_a_second_pass_skips_them(queued):
    # Simulate a worker that claims and then dies before sending.
    claimed = delivery_module.claim_due_deliveries(limit=10)
    assert claimed == [queued.id]

    sender = FakeSender()
    assert process_due_deliveries(sender=sender) == 0
    assert sender.calls == []


@pytest.mark.django_db
def test_worker_claims_one_row_at_a_time_so_others_stay_claimable(endpoint, queued):
    second = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='timesheet.submitted', payload={'id': 'evt_second'},
        next_attempt_at=timezone.now() - timedelta(seconds=1),
    )
    claimed_by_other_worker = []

    def slow_sender(url, body, headers, timeout):
        # While this worker is busy sending, a second worker polls. It must get
        # only rows this worker has not started on, never the one in flight.
        claimed_by_other_worker.extend(delivery_module.claim_due_deliveries(limit=10))
        return SendResult(status=200)

    attempted = process_due_deliveries(sender=slow_sender)

    assert attempted == 1
    assert len(claimed_by_other_worker) == 1
    in_flight = {second.id, queued.id} - set(claimed_by_other_worker)
    assert WebhookDelivery.objects.get(id=in_flight.pop()).status == WebhookDelivery.STATUS_SUCCEEDED


@pytest.mark.django_db
def test_unexpected_error_on_one_delivery_does_not_stop_the_batch(endpoint, queued):
    WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='timesheet.submitted', payload={'id': 'evt_second'},
        next_attempt_at=timezone.now(),
    )
    calls = []

    def flaky_sender(url, body, headers, timeout):
        calls.append(headers['YJ-Webhook-Id'])
        if len(calls) == 1:
            raise RuntimeError('unexpected')
        return SendResult(status=200)

    attempted = process_due_deliveries(sender=flaky_sender)

    assert attempted == 2
    assert len(calls) == 2
    statuses = dict(WebhookDelivery.objects.values_list('payload__id', 'status'))
    failed_id, ok_id = calls
    assert statuses[ok_id] == WebhookDelivery.STATUS_SUCCEEDED
    # The failed row stays pending under its lease, to be retried later.
    failed = WebhookDelivery.objects.get(payload__id=failed_id)
    assert failed.status == WebhookDelivery.STATUS_PENDING
    assert failed.next_attempt_at > timezone.now()
    assert failed.attempts.count() == 0


@pytest.mark.django_db
def test_management_command_once_processes_due_deliveries(queued, monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(delivery_module, 'http_post', sender)

    call_command('deliver_webhooks', '--once')

    queued.refresh_from_db()
    assert queued.status == WebhookDelivery.STATUS_SUCCEEDED
    assert len(sender.calls) == 1


# --- Send test event (API) ---

@pytest.mark.django_db
def test_send_test_event_makes_inline_attempt(admin_client, endpoint, monkeypatch):
    sender = FakeSender(SendResult(status=200, body='{"received":true}'))
    monkeypatch.setattr(delivery_module, 'http_post', sender)

    resp = admin_client.post(f'/api/webhook-endpoints/{endpoint.id}/test/')

    assert resp.status_code == 201
    assert resp.data['event_type'] == 'webhook.test'
    assert resp.data['status'] == 'succeeded'
    assert resp.data['attempts'][0]['response_status'] == 200
    assert sender.calls[0]['headers']['YJ-Webhook-Event'] == 'webhook.test'


@pytest.mark.django_db
def test_failed_test_event_is_left_for_worker_retry(admin_client, endpoint, monkeypatch):
    monkeypatch.setattr(delivery_module, 'http_post', FakeSender(SendResult(status=None, error='refused')))

    resp = admin_client.post(f'/api/webhook-endpoints/{endpoint.id}/test/')

    assert resp.status_code == 201
    assert resp.data['status'] == 'pending'
    assert resp.data['attempt_count'] == 1
    assert resp.data['next_attempt_at'] is not None


@pytest.mark.django_db
def test_send_test_event_rejected_for_disabled_endpoint(admin_client, endpoint, monkeypatch):
    endpoint.active = False
    endpoint.save()
    sender = FakeSender()
    monkeypatch.setattr(delivery_module, 'http_post', sender)

    resp = admin_client.post(f'/api/webhook-endpoints/{endpoint.id}/test/')

    assert resp.status_code == 400
    assert sender.calls == []
    assert WebhookDelivery.objects.count() == 0


@pytest.mark.django_db
def test_send_test_event_is_scoped_to_company(admin_client, meridian, endpoint):
    other = WebhookEndpoint.objects.create(company=meridian, url='https://hooks.meridian.test/yj')

    assert admin_client.post(f'/api/webhook-endpoints/{other.id}/test/').status_code == 404


@pytest.mark.django_db
def test_freelancer_cannot_send_test_event(freelancer_client, endpoint):
    assert freelancer_client.post(f'/api/webhook-endpoints/{endpoint.id}/test/').status_code == 403


# --- Real HTTP client against a local server ---

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/ok')
            self.end_headers()
            return
        code = 500 if self.path == '/error' else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b'x' * 2000 if self.path == '/big' else b'hello')

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def test_http_post_returns_status_and_body(local_server):
    result = http_post(f'{local_server}/ok', b'{}', {'Content-Type': 'application/json'}, 5)
    assert result.status == 200
    assert result.body == 'hello'
    assert result.ok


def test_http_post_reports_error_status(local_server):
    result = http_post(f'{local_server}/error', b'{}', {}, 5)
    assert result.status == 500
    assert not result.ok


def test_http_post_does_not_follow_redirects(local_server):
    result = http_post(f'{local_server}/redirect', b'{}', {}, 5)
    assert result.status == 302
    assert not result.ok


def test_http_post_truncates_response_body(local_server):
    result = http_post(f'{local_server}/big', b'{}', {}, 5)
    assert len(result.body) == 1024


def test_http_post_connection_refused_is_an_error_result():
    with HTTPServer(('127.0.0.1', 0), _Handler) as server:
        port = server.server_port  # closed on exit, so nothing listens
    result = http_post(f'http://127.0.0.1:{port}/ok', b'{}', {}, 5)
    assert result.status is None
    assert result.error.startswith('Connection error')


@pytest.mark.django_db
def test_url_change_after_queueing_is_used_for_the_send(queued, endpoint):
    WebhookEndpoint.objects.filter(pk=endpoint.pk).update(url='https://moved.northstar.test/yj')
    sender = FakeSender()

    attempt_delivery(queued, sender=sender)

    assert sender.calls[0]['url'] == 'https://moved.northstar.test/yj'


@pytest.mark.django_db
def test_endpoint_deleted_mid_run_is_skipped(queued, endpoint):
    WebhookEndpoint.objects.filter(pk=endpoint.pk).delete()
    sender = FakeSender()

    attempt_delivery(queued, sender=sender)

    assert sender.calls == []
