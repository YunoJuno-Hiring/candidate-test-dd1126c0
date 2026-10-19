import hashlib
import hmac

SIGNATURE_VERSION = 'v1'


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """HMAC-SHA256 over "<timestamp>.<raw body>", hex encoded."""
    signed = f'{timestamp}.'.encode() + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def signature_header(secret: str, timestamp: int, body: bytes) -> str:
    """Value for the YJ-Webhook-Signature header.

    Receivers recompute the HMAC over the raw body they received, compare it
    with hmac.compare_digest, and reject timestamps outside a small window
    (for example 5 minutes) to block replays.
    """
    return f't={timestamp},{SIGNATURE_VERSION}={compute_signature(secret, timestamp, body)}'
