import secrets
import uuid

from django.db import models

from accounts.models import Company


def generate_secret():
    return f'whsec_{secrets.token_urlsafe(32)}'


class WebhookEndpoint(models.Model):
    """A company-owned destination that receives signed event deliveries."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='webhook_endpoints')
    url = models.URLField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    # Stored in plain text because HMAC signing needs the raw value.
    # Encryption at rest is deferred (see CANDIDATE_NOTES.md).
    secret = models.CharField(max_length=100, default=generate_secret, editable=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company.name} → {self.url}'


class WebhookDelivery(models.Model):
    """One event queued for one endpoint (the outbox row).

    Created in the same transaction as the state change that produced the
    event, then sent by the `deliver_webhooks` worker.
    """

    STATUS_PENDING = 'pending'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    # Shared by every endpoint's delivery of the same event and stable across
    # retries, so receivers can dedupe on it.
    event_id = models.UUIDField(default=uuid.uuid4)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    # When the worker may next pick this row up. Null once the delivery is final.
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_response_code = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'webhook deliveries'
        indexes = [
            models.Index(fields=['status', 'next_attempt_at']),
        ]

    def __str__(self):
        return f'{self.event_type} {self.event_id} → {self.endpoint.url} ({self.status})'


class WebhookDeliveryAttempt(models.Model):
    """One HTTP attempt for a delivery: the delivery log shown in the UI."""

    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.CASCADE, related_name='attempts')
    attempt_number = models.PositiveIntegerField()
    # Null when no HTTP response was received (timeout, connection error).
    response_status = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['attempt_number']

    def __str__(self):
        return f'Attempt {self.attempt_number} for delivery {self.delivery_id}'
