from __future__ import annotations

"""Ship24 API wrapper for package tracking.

Handles tracker creation, result retrieval, and status normalization.
Auth: Bearer token via SHIP24_API_KEY from app.config.
Rate limiting: 0.5s delay between API calls.
Retries: 3 attempts with exponential backoff (1s, 2s, 4s) on 429/5xx.
"""

import logging
import time

import requests

from app import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ship24.com/public/v1"

# Exponential backoff delays in seconds for retries 1, 2, 3
_RETRY_DELAYS = [1, 2, 4]

# Minimum gap between any two API calls (rate limiting)
_RATE_LIMIT_SECONDS = 0.5

# Timestamp of the last API call (module-level to throttle across functions)
_last_call_time = 0.0

# Ship24 statuses → our internal statuses
_STATUS_MAP = {
    "pending": "pending",
    "info_received": "pending",
    "in_transit": "in_transit",
    "inTransit": "in_transit",
    "out_for_delivery": "out_for_delivery",
    "outForDelivery": "out_for_delivery",
    "delivered": "delivered",
    "exception": "exception",
    "failed_attempt": "exception",
    "failedAttempt": "exception",
    "available_for_pickup": "out_for_delivery",
    "availableForPickup": "out_for_delivery",
}


class Ship24Error(Exception):
    """Raised when a Ship24 API call fails after all retries."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _get_headers() -> dict:
    """Build authorization headers for Ship24 API calls."""
    api_key = config.SHIP24_API_KEY
    if not api_key:
        raise Ship24Error("SHIP24_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _rate_limit():
    """Enforce a minimum gap between consecutive API calls."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_call_time = time.time()


def _is_retryable(status_code: int) -> bool:
    """Return True if the HTTP status code warrants a retry."""
    return status_code == 429 or status_code >= 500


def _request_with_retries(method: str, url: str, **kwargs) -> requests.Response:
    """Execute an HTTP request with retry logic and rate limiting.

    Retries up to 3 times on 429 (rate-limited) or 5xx (server error)
    responses with exponential backoff of 1s, 2s, 4s.
    """
    last_response = None

    for attempt in range(len(_RETRY_DELAYS) + 1):
        _rate_limit()

        try:
            if method == "POST":
                response = requests.post(url, **kwargs)
            else:
                response = requests.get(url, **kwargs)
        except requests.RequestException as exc:
            raise Ship24Error(f"Network error calling Ship24: {exc}") from exc

        last_response = response

        if response.ok:
            return response

        if _is_retryable(response.status_code) and attempt < len(_RETRY_DELAYS):
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "Ship24 %s %s returned %d, retrying in %ds (attempt %d/%d)",
                method,
                url,
                response.status_code,
                delay,
                attempt + 1,
                len(_RETRY_DELAYS),
            )
            time.sleep(delay)
            continue

        # Non-retryable error or exhausted retries
        break

    # All retries exhausted or non-retryable status
    status = last_response.status_code if last_response else None
    body = last_response.text if last_response else "no response"
    raise Ship24Error(
        f"Ship24 API error: {status} — {body}",
        status_code=status,
    )


def create_tracker(
    tracking_number: str, courier_code: str | None = None
) -> dict:
    """Create a new tracker for a tracking number.

    Args:
        tracking_number: The carrier tracking number (e.g. "1Z999AA10123456784").
        courier_code: Optional courier code (e.g. "ups") to narrow detection.

    Returns:
        The tracker object from Ship24 (contains trackerId, trackingNumber, etc.).

    Raises:
        Ship24Error: If the API call fails after retries.
    """
    url = f"{BASE_URL}/trackers"
    payload = {
        "trackingNumber": tracking_number,
        "courierCode": [courier_code] if courier_code else [],
    }

    logger.info("Creating Ship24 tracker for %s", tracking_number)
    response = _request_with_retries("POST", url, headers=_get_headers(), json=payload)
    data = response.json()
    tracker = data.get("data", {}).get("tracker", data)
    logger.info("Ship24 tracker created: %s", tracker.get("trackerId"))
    return tracker


def get_tracking_results(tracker_id: str) -> dict:
    """Fetch tracking results for an existing tracker.

    Args:
        tracker_id: The Ship24 tracker UUID returned from create_tracker().

    Returns:
        The full results object (contains trackings, shipments, events, etc.).

    Raises:
        Ship24Error: If the API call fails after retries.
    """
    url = f"{BASE_URL}/trackers/{tracker_id}/results"

    logger.info("Fetching Ship24 results for tracker %s", tracker_id)
    response = _request_with_retries("GET", url, headers=_get_headers())
    data = response.json()
    logger.info("Ship24 results fetched for tracker %s", tracker_id)
    return data


def normalize_status(ship24_status: str) -> str:
    """Map a Ship24 status string to our internal status.

    Args:
        ship24_status: A status string from Ship24 (e.g. "inTransit",
            "delivered", "out_for_delivery").

    Returns:
        One of: "pending", "in_transit", "out_for_delivery", "delivered",
        "exception". Defaults to "pending" for unrecognized statuses.
    """
    normalized = _STATUS_MAP.get(ship24_status)
    if normalized is None:
        logger.warning("Unknown Ship24 status '%s', defaulting to 'pending'", ship24_status)
        return "pending"
    return normalized
