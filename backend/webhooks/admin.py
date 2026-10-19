from django.contrib import admin
from .models import WebhookDelivery, WebhookDeliveryAttempt, WebhookEndpoint

admin.site.register(WebhookEndpoint)
admin.site.register(WebhookDelivery)
admin.site.register(WebhookDeliveryAttempt)
