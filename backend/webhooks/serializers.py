from urllib.parse import urlparse

from rest_framework import serializers

from .models import WebhookDelivery, WebhookDeliveryAttempt, WebhookEndpoint

ALLOWED_URL_SCHEMES = ('http', 'https')


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """Read/update serialiser. Never exposes the full secret."""

    secret_last4 = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'url', 'description', 'active', 'secret_last4', 'created_at', 'updated_at']
        read_only_fields = ['id', 'secret_last4', 'created_at', 'updated_at']

    def get_secret_last4(self, obj):
        return obj.secret[-4:]

    def validate_url(self, value):
        # DRF's URLField also accepts ftp/ftps; only HTTP(S) can receive a webhook.
        # Blocking private/loopback hosts (SSRF) is deferred: local development
        # has to deliver to localhost.
        if urlparse(value).scheme.lower() not in ALLOWED_URL_SCHEMES:
            raise serializers.ValidationError('URL must use http or https.')
        return value


class WebhookEndpointCreatedSerializer(WebhookEndpointSerializer):
    """Returned once, from the create response only, so the admin can copy the secret."""

    class Meta(WebhookEndpointSerializer.Meta):
        fields = WebhookEndpointSerializer.Meta.fields + ['secret']


class WebhookDeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDeliveryAttempt
        fields = ['attempt_number', 'response_status', 'response_body', 'error', 'duration_ms', 'created_at']


class WebhookDeliverySerializer(serializers.ModelSerializer):
    attempts = WebhookDeliveryAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'event_id', 'event_type', 'status', 'attempt_count', 'next_attempt_at',
            'last_response_code', 'created_at', 'updated_at', 'payload', 'attempts',
        ]
