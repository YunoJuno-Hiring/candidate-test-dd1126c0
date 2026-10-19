from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .delivery import send_test_event
from .models import WebhookEndpoint
from .serializers import (
    WebhookDeliverySerializer,
    WebhookEndpointCreatedSerializer,
    WebhookEndpointSerializer,
)

DELIVERY_LOG_LIMIT = 50


def _admin_company(user):
    """The admin's company, or None if the user is not a company admin."""
    if hasattr(user, 'company_admin'):
        return user.company_admin.company
    return None


def _get_endpoint(company, pk):
    """Fetch an endpoint scoped to the admin's company; other companies' ids look missing."""
    try:
        return WebhookEndpoint.objects.get(pk=pk, company=company)
    except WebhookEndpoint.DoesNotExist:
        return None


def _not_found():
    return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)


def _forbidden():
    return Response(
        {'detail': 'Only company admins can manage webhook endpoints.'},
        status=status.HTTP_403_FORBIDDEN,
    )


class WebhookEndpointListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        qs = WebhookEndpoint.objects.filter(company=company)
        return Response(WebhookEndpointSerializer(qs, many=True).data)

    def post(self, request):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        serializer = WebhookEndpointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save(company=company)
        # The only response that ever contains the full secret.
        return Response(WebhookEndpointCreatedSerializer(endpoint).data, status=status.HTTP_201_CREATED)


class WebhookEndpointDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        endpoint = _get_endpoint(company, pk)
        if endpoint is None:
            return _not_found()
        return Response(WebhookEndpointSerializer(endpoint).data)

    def patch(self, request, pk):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        endpoint = _get_endpoint(company, pk)
        if endpoint is None:
            return _not_found()
        serializer = WebhookEndpointSerializer(endpoint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        endpoint = _get_endpoint(company, pk)
        if endpoint is None:
            return _not_found()
        endpoint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookDeliveryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        endpoint = _get_endpoint(company, pk)
        if endpoint is None:
            return _not_found()
        qs = endpoint.deliveries.prefetch_related('attempts').order_by('-created_at', '-id')[:DELIVERY_LOG_LIMIT]
        return Response(WebhookDeliverySerializer(qs, many=True).data)


class WebhookEndpointTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        company = _admin_company(request.user)
        if company is None:
            return _forbidden()
        endpoint = _get_endpoint(company, pk)
        if endpoint is None:
            return _not_found()
        if not endpoint.active:
            return Response(
                {'detail': 'Enable the endpoint before sending a test event.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # The first attempt runs inline so the UI can show the result straight away;
        # a failure is retried by the worker on the normal schedule.
        delivery = send_test_event(endpoint)
        return Response(WebhookDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)
