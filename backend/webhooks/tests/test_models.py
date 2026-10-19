import pytest

from webhooks.models import WebhookDelivery, WebhookDeliveryAttempt, WebhookEndpoint


@pytest.mark.django_db
def test_endpoint_gets_unique_generated_secret(northstar):
    first = WebhookEndpoint.objects.create(company=northstar, url='https://a.example.com/hook')
    second = WebhookEndpoint.objects.create(company=northstar, url='https://b.example.com/hook')

    assert first.secret.startswith('whsec_')
    assert len(first.secret) > 40
    assert first.secret != second.secret
    assert first.active is True


@pytest.mark.django_db
def test_delivery_defaults_to_pending_with_event_id(northstar):
    endpoint = WebhookEndpoint.objects.create(company=northstar, url='https://a.example.com/hook')
    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='webhook.test', payload={'type': 'webhook.test'}
    )

    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempt_count == 0
    assert delivery.event_id is not None


@pytest.mark.django_db
def test_deleting_endpoint_deletes_its_delivery_log(northstar):
    endpoint = WebhookEndpoint.objects.create(company=northstar, url='https://a.example.com/hook')
    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='webhook.test', payload={}
    )
    WebhookDeliveryAttempt.objects.create(delivery=delivery, attempt_number=1, duration_ms=5)

    endpoint.delete()

    assert WebhookDelivery.objects.count() == 0
    assert WebhookDeliveryAttempt.objects.count() == 0
