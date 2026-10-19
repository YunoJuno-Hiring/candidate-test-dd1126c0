import pytest

from webhooks.models import WebhookDelivery, WebhookDeliveryAttempt, WebhookEndpoint


@pytest.fixture
def endpoint(northstar):
    return WebhookEndpoint.objects.create(
        company=northstar, url='https://hooks.northstar.test/yj', description='ERP sync'
    )


@pytest.fixture
def other_endpoint(meridian):
    return WebhookEndpoint.objects.create(company=meridian, url='https://hooks.meridian.test/yj')


# --- Create / list / detail ---

@pytest.mark.django_db
def test_admin_creates_endpoint_and_sees_secret_once(admin_client, northstar):
    resp = admin_client.post(
        '/api/webhook-endpoints/',
        {'url': 'https://hooks.northstar.test/yj', 'description': 'ERP sync'},
        format='json',
    )

    assert resp.status_code == 201
    assert resp.data['secret'].startswith('whsec_')
    assert resp.data['secret_last4'] == resp.data['secret'][-4:]
    assert resp.data['active'] is True
    endpoint = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert endpoint.company == northstar
    assert endpoint.secret == resp.data['secret']


@pytest.mark.django_db
def test_create_ignores_client_supplied_company_and_secret(admin_client, northstar, meridian):
    resp = admin_client.post(
        '/api/webhook-endpoints/',
        {'url': 'https://hooks.northstar.test/yj', 'company': meridian.id, 'secret': 'whsec_mine'},
        format='json',
    )

    assert resp.status_code == 201
    endpoint = WebhookEndpoint.objects.get(pk=resp.data['id'])
    assert endpoint.company == northstar
    assert endpoint.secret != 'whsec_mine'


@pytest.mark.django_db
def test_list_and_detail_never_expose_secret(admin_client, endpoint):
    list_resp = admin_client.get('/api/webhook-endpoints/')
    detail_resp = admin_client.get(f'/api/webhook-endpoints/{endpoint.id}/')

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert 'secret' not in list_resp.data[0]
    assert 'secret' not in detail_resp.data
    assert detail_resp.data['secret_last4'] == endpoint.secret[-4:]


@pytest.mark.django_db
def test_list_is_scoped_to_admins_company(admin_client, endpoint, other_endpoint):
    resp = admin_client.get('/api/webhook-endpoints/')

    assert resp.status_code == 200
    assert [ep['id'] for ep in resp.data] == [endpoint.id]


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['not-a-url', 'ftp://files.example.com/hook', ''])
def test_create_rejects_invalid_url(admin_client, url):
    resp = admin_client.post('/api/webhook-endpoints/', {'url': url}, format='json')

    assert resp.status_code == 400
    assert 'url' in resp.data
    assert WebhookEndpoint.objects.count() == 0


@pytest.mark.django_db
def test_create_rejects_url_over_500_chars(admin_client):
    url = 'https://example.com/' + 'a' * 500
    resp = admin_client.post('/api/webhook-endpoints/', {'url': url}, format='json')

    assert resp.status_code == 400
    assert 'url' in resp.data


@pytest.mark.django_db
def test_localhost_url_is_allowed_for_local_development(admin_client):
    resp = admin_client.post('/api/webhook-endpoints/', {'url': 'http://localhost:8027/hook'}, format='json')

    assert resp.status_code == 201


# --- Edit / delete ---

@pytest.mark.django_db
def test_admin_edits_url_description_and_active(admin_client, endpoint):
    original_secret = endpoint.secret
    resp = admin_client.patch(
        f'/api/webhook-endpoints/{endpoint.id}/',
        {'url': 'https://new.northstar.test/yj', 'description': 'Slack', 'active': False},
        format='json',
    )

    assert resp.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.url == 'https://new.northstar.test/yj'
    assert endpoint.description == 'Slack'
    assert endpoint.active is False
    assert endpoint.secret == original_secret


@pytest.mark.django_db
def test_edit_rejects_invalid_url(admin_client, endpoint):
    resp = admin_client.patch(
        f'/api/webhook-endpoints/{endpoint.id}/', {'url': 'ftp://x.test/hook'}, format='json'
    )

    assert resp.status_code == 400
    endpoint.refresh_from_db()
    assert endpoint.url == 'https://hooks.northstar.test/yj'


@pytest.mark.django_db
def test_admin_deletes_endpoint(admin_client, endpoint):
    resp = admin_client.delete(f'/api/webhook-endpoints/{endpoint.id}/')

    assert resp.status_code == 204
    assert not WebhookEndpoint.objects.filter(pk=endpoint.id).exists()


# --- Delivery log ---

@pytest.mark.django_db
def test_delivery_log_newest_first_with_nested_attempts(admin_client, endpoint):
    older = WebhookDelivery.objects.create(endpoint=endpoint, event_type='webhook.test', payload={})
    newer = WebhookDelivery.objects.create(
        endpoint=endpoint, event_type='timesheet.submitted', payload={}, attempt_count=1,
        last_response_code=500,
    )
    WebhookDeliveryAttempt.objects.create(
        delivery=newer, attempt_number=1, response_status=500, duration_ms=12
    )

    resp = admin_client.get(f'/api/webhook-endpoints/{endpoint.id}/deliveries/')

    assert resp.status_code == 200
    assert [d['id'] for d in resp.data] == [newer.id, older.id]
    assert resp.data[0]['attempts'][0]['attempt_number'] == 1
    assert resp.data[0]['attempts'][0]['response_status'] == 500
    assert resp.data[1]['attempts'] == []


@pytest.mark.django_db
def test_delivery_log_is_limited_to_50(admin_client, endpoint):
    WebhookDelivery.objects.bulk_create(
        WebhookDelivery(endpoint=endpoint, event_type='webhook.test', payload={}) for _ in range(55)
    )

    resp = admin_client.get(f'/api/webhook-endpoints/{endpoint.id}/deliveries/')

    assert resp.status_code == 200
    assert len(resp.data) == 50


# --- Permissions and scoping ---

@pytest.mark.django_db
@pytest.mark.parametrize('method, suffix', [
    ('get', ''),
    ('patch', ''),
    ('delete', ''),
    ('get', 'deliveries/'),
])
def test_other_companys_endpoint_is_not_found(admin_client, other_endpoint, method, suffix):
    resp = getattr(admin_client, method)(
        f'/api/webhook-endpoints/{other_endpoint.id}/{suffix}', {'active': False}, format='json'
    )

    assert resp.status_code == 404
    other_endpoint.refresh_from_db()
    assert other_endpoint.active is True


@pytest.mark.django_db
@pytest.mark.parametrize('method, path', [
    ('get', '/api/webhook-endpoints/'),
    ('post', '/api/webhook-endpoints/'),
    ('get', '/api/webhook-endpoints/{id}/'),
    ('patch', '/api/webhook-endpoints/{id}/'),
    ('delete', '/api/webhook-endpoints/{id}/'),
    ('get', '/api/webhook-endpoints/{id}/deliveries/'),
])
def test_freelancer_is_forbidden(freelancer_client, endpoint, method, path):
    resp = getattr(freelancer_client, method)(
        path.format(id=endpoint.id), {'url': 'https://x.test/hook'}, format='json'
    )

    assert resp.status_code == 403
    assert WebhookEndpoint.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('method, path', [
    ('get', '/api/webhook-endpoints/'),
    ('post', '/api/webhook-endpoints/'),
    ('get', '/api/webhook-endpoints/{id}/'),
    ('delete', '/api/webhook-endpoints/{id}/'),
])
def test_unauthenticated_is_rejected(api_client, endpoint, method, path):
    resp = getattr(api_client, method)(path.format(id=endpoint.id))

    assert resp.status_code == 401
