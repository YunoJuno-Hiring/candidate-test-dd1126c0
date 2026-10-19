import datetime
from decimal import Decimal

import pytest

from contracts.models import TimesheetEntry
from webhooks import events
from webhooks.models import WebhookDelivery, WebhookEndpoint


@pytest.fixture
def endpoint(northstar):
    return WebhookEndpoint.objects.create(company=northstar, url='https://hooks.northstar.test/yj')


def submit(freelancer_client, contract, date='2026-05-01'):
    return freelancer_client.post('/api/timesheets/', {
        'contract': contract.id,
        'date': date,
        'hours': '7.5',
    })


@pytest.mark.django_db
def test_submit_queues_versioned_event_for_active_endpoint(freelancer_client, active_contract, endpoint):
    resp = submit(freelancer_client, active_contract)

    assert resp.status_code == 201
    delivery = WebhookDelivery.objects.get()
    assert delivery.endpoint == endpoint
    assert delivery.event_type == 'timesheet.submitted'
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.next_attempt_at is not None
    assert delivery.payload['id'] == f'evt_{delivery.event_id.hex}'
    assert delivery.payload['type'] == 'timesheet.submitted'
    assert delivery.payload['version'] == 1
    assert 'created_at' in delivery.payload
    assert delivery.payload['data'] == {
        'timesheet_entry': {
            'id': resp.data['id'],
            'contract_id': active_contract.id,
            'freelancer_id': active_contract.freelancer_id,
            'date': '2026-05-01',
            'hours': '7.50',
            'status': 'submitted',
        }
    }


@pytest.mark.django_db
def test_one_event_fans_out_to_each_active_endpoint_with_shared_event_id(
    freelancer_client, active_contract, northstar, endpoint
):
    second = WebhookEndpoint.objects.create(company=northstar, url='https://second.northstar.test/yj')

    submit(freelancer_client, active_contract)

    deliveries = list(WebhookDelivery.objects.all())
    assert {d.endpoint_id for d in deliveries} == {endpoint.id, second.id}
    assert len({d.event_id for d in deliveries}) == 1


@pytest.mark.django_db
def test_inactive_and_other_company_endpoints_get_nothing(
    freelancer_client, active_contract, northstar, meridian
):
    WebhookEndpoint.objects.create(company=northstar, url='https://off.northstar.test/yj', active=False)
    WebhookEndpoint.objects.create(company=meridian, url='https://hooks.meridian.test/yj')

    resp = submit(freelancer_client, active_contract)

    assert resp.status_code == 201
    assert WebhookDelivery.objects.count() == 0


@pytest.mark.django_db
def test_rejected_submission_queues_nothing(freelancer_client, active_contract, endpoint):
    resp = freelancer_client.post('/api/timesheets/', {'contract': active_contract.id, 'date': 'bad'})

    assert resp.status_code == 400
    assert WebhookDelivery.objects.count() == 0


@pytest.mark.django_db
def test_entry_is_rolled_back_if_queueing_the_event_fails(
    freelancer_client, active_contract, endpoint, monkeypatch
):
    def boom(entry):
        raise RuntimeError('outbox write failed')

    monkeypatch.setattr('contracts.views.emit_timesheet_submitted', boom)

    with pytest.raises(RuntimeError):
        submit(freelancer_client, active_contract)

    assert TimesheetEntry.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize('previous_status', ['draft', 'rejected'])
def test_patch_into_submitted_queues_event(freelancer_client, active_contract, endpoint, previous_status):
    entry = TimesheetEntry.objects.create(
        contract=active_contract, date=datetime.date(2026, 4, 8), hours=Decimal('8.0'),
        status=previous_status,
    )

    resp = freelancer_client.patch(f'/api/timesheets/{entry.id}/', {'status': 'submitted'}, format='json')

    assert resp.status_code == 200
    delivery = WebhookDelivery.objects.get()
    assert delivery.payload['data']['timesheet_entry']['id'] == entry.id


@pytest.mark.django_db
def test_patch_that_stays_submitted_queues_nothing(freelancer_client, submitted_entry, endpoint):
    resp = freelancer_client.patch(
        f'/api/timesheets/{submitted_entry.id}/', {'hours': '6.0'}, format='json'
    )

    assert resp.status_code == 200
    assert WebhookDelivery.objects.count() == 0


@pytest.mark.django_db
def test_approving_queues_nothing(admin_client, submitted_entry, endpoint):
    resp = admin_client.patch(
        f'/api/timesheets/{submitted_entry.id}/', {'status': 'approved'}, format='json'
    )

    assert resp.status_code == 200
    assert WebhookDelivery.objects.count() == 0


@pytest.mark.django_db
def test_emit_event_without_endpoints_returns_empty(northstar):
    assert events.emit_event(northstar, 'timesheet.submitted', {}) == []
