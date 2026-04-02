"""Unit tests for Ship24 API client.

All HTTP calls are mocked — no real network requests are made.
Uses pytest + pytest-mock (mocker fixture).
"""

import pytest
import requests

from app.tracker.ship24_client import (
    Ship24Error,
    create_tracker,
    get_tracking_results,
    normalize_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(json_data, status_code=200):
    """Build a mock response object that looks successful."""
    mock = type("MockResponse", (), {
        "ok": True,
        "status_code": status_code,
        "json": lambda self: json_data,
        "text": str(json_data),
    })()
    return mock


def _error_response(status_code, body="error"):
    """Build a mock response object that represents an HTTP error."""
    mock = type("MockResponse", (), {
        "ok": False,
        "status_code": status_code,
        "json": lambda self: {"error": body},
        "text": body,
    })()
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_api_key(mocker):
    """Ensure SHIP24_API_KEY is always set and rate-limit sleeps are skipped."""
    mocker.patch("app.tracker.ship24_client.config")
    import app.tracker.ship24_client as mod
    mod.config.SHIP24_API_KEY = "test-api-key-123"

    # Skip time.sleep so tests run instantly
    mocker.patch("app.tracker.ship24_client.time.sleep")

    # Reset rate-limit timestamp between tests
    mod._last_call_time = 0.0


# ---------------------------------------------------------------------------
# create_tracker tests
# ---------------------------------------------------------------------------

class TestCreateTracker:

    def test_success_returns_tracker_with_id(self, mocker):
        """Happy path: POST succeeds, returns tracker object with trackerId."""
        tracker_data = {
            "data": {
                "tracker": {
                    "trackerId": "abc-123",
                    "trackingNumber": "1Z999AA10123456784",
                    "isSubscribed": True,
                    "createdAt": "2026-04-01T10:00:00.000Z",
                }
            }
        }
        mock_post = mocker.patch(
            "requests.post", return_value=_ok_response(tracker_data, 201)
        )

        result = create_tracker("1Z999AA10123456784")

        assert result["trackerId"] == "abc-123"
        assert result["trackingNumber"] == "1Z999AA10123456784"

        # Verify correct URL and payload
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "trackers" in call_kwargs.args[0] or "trackers" in call_kwargs.kwargs.get("url", call_kwargs.args[0])
        sent_json = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert sent_json["trackingNumber"] == "1Z999AA10123456784"
        assert sent_json["courierCode"] == []

    def test_with_courier_code_sends_correct_body(self, mocker):
        """When courier_code is provided, it should be wrapped in a list."""
        tracker_data = {
            "data": {
                "tracker": {
                    "trackerId": "def-456",
                    "trackingNumber": "TRACK123",
                }
            }
        }
        mock_post = mocker.patch(
            "requests.post", return_value=_ok_response(tracker_data, 201)
        )

        result = create_tracker("TRACK123", courier_code="ups")

        assert result["trackerId"] == "def-456"
        sent_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert sent_json["courierCode"] == ["ups"]

    def test_auth_header_uses_bearer_token(self, mocker):
        """Authorization header must be 'Bearer <api_key>'."""
        tracker_data = {"data": {"tracker": {"trackerId": "x"}}}
        mock_post = mocker.patch(
            "requests.post", return_value=_ok_response(tracker_data, 201)
        )

        create_tracker("TRACK123")

        headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args[1].get("headers")
        assert headers["Authorization"] == "Bearer test-api-key-123"


# ---------------------------------------------------------------------------
# get_tracking_results tests
# ---------------------------------------------------------------------------

class TestGetTrackingResults:

    def test_success_returns_results_with_status(self, mocker):
        """Happy path: GET returns full results object."""
        results_data = {
            "data": {
                "trackings": [
                    {
                        "tracker": {"trackerId": "abc-123"},
                        "shipment": {"statusMilestone": "in_transit"},
                        "events": [
                            {
                                "status": "inTransit",
                                "datetime": "2026-04-01T12:00:00.000Z",
                                "description": "Package in transit",
                            }
                        ],
                    }
                ]
            }
        }
        mocker.patch("requests.get", return_value=_ok_response(results_data))

        result = get_tracking_results("abc-123")

        assert "data" in result
        trackings = result["data"]["trackings"]
        assert len(trackings) == 1
        assert trackings[0]["shipment"]["statusMilestone"] == "in_transit"

    def test_calls_correct_url(self, mocker):
        """The URL must include the tracker ID."""
        results_data = {"data": {"trackings": []}}
        mock_get = mocker.patch(
            "requests.get", return_value=_ok_response(results_data)
        )

        get_tracking_results("my-tracker-id")

        called_url = mock_get.call_args.args[0] if mock_get.call_args.args else mock_get.call_args.kwargs["url"]
        assert "trackers/my-tracker-id/results" in called_url


# ---------------------------------------------------------------------------
# normalize_status tests
# ---------------------------------------------------------------------------

class TestNormalizeStatus:

    @pytest.mark.parametrize(
        "ship24_status, expected",
        [
            ("pending", "pending"),
            ("info_received", "pending"),
            ("in_transit", "in_transit"),
            ("inTransit", "in_transit"),
            ("out_for_delivery", "out_for_delivery"),
            ("outForDelivery", "out_for_delivery"),
            ("delivered", "delivered"),
            ("exception", "exception"),
            ("failed_attempt", "exception"),
            ("failedAttempt", "exception"),
            ("available_for_pickup", "out_for_delivery"),
            ("availableForPickup", "out_for_delivery"),
        ],
    )
    def test_known_statuses_map_correctly(self, ship24_status, expected):
        assert normalize_status(ship24_status) == expected

    def test_unknown_status_defaults_to_pending(self):
        """Unrecognized statuses should fall back to 'pending'."""
        assert normalize_status("some_weird_status") == "pending"

    def test_empty_string_defaults_to_pending(self):
        assert normalize_status("") == "pending"


# ---------------------------------------------------------------------------
# Error handling & retry tests
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_401_raises_ship24_error_immediately(self, mocker):
        """A 401 is not retryable — should raise Ship24Error on first attempt."""
        mock_post = mocker.patch(
            "requests.post", return_value=_error_response(401, "Unauthorized")
        )

        with pytest.raises(Ship24Error) as exc_info:
            create_tracker("TRACK123")

        assert exc_info.value.status_code == 401
        assert "401" in str(exc_info.value)
        # Should only be called once (no retries for 401)
        assert mock_post.call_count == 1

    def test_429_retries_then_succeeds(self, mocker):
        """429 should trigger retries; success on second attempt."""
        success_data = {
            "data": {
                "tracker": {
                    "trackerId": "retry-ok",
                    "trackingNumber": "TRACK123",
                }
            }
        }
        mock_post = mocker.patch(
            "requests.post",
            side_effect=[
                _error_response(429, "Too Many Requests"),
                _ok_response(success_data, 201),
            ],
        )

        result = create_tracker("TRACK123")

        assert result["trackerId"] == "retry-ok"
        assert mock_post.call_count == 2

    def test_500_retries_3x_then_raises(self, mocker):
        """500 should retry 3 times (4 total attempts) then raise Ship24Error."""
        mock_post = mocker.patch(
            "requests.post",
            return_value=_error_response(500, "Internal Server Error"),
        )

        with pytest.raises(Ship24Error) as exc_info:
            create_tracker("TRACK123")

        assert exc_info.value.status_code == 500
        # 1 initial attempt + 3 retries = 4 total
        assert mock_post.call_count == 4

    def test_503_retries_then_succeeds_on_third(self, mocker):
        """503 errors should retry, succeed when server recovers."""
        success_data = {"data": {"trackings": []}}
        mock_get = mocker.patch(
            "requests.get",
            side_effect=[
                _error_response(503, "Service Unavailable"),
                _error_response(503, "Service Unavailable"),
                _ok_response(success_data),
            ],
        )

        result = get_tracking_results("tracker-id")

        assert "data" in result
        assert mock_get.call_count == 3

    def test_missing_api_key_raises_ship24_error(self, mocker):
        """If SHIP24_API_KEY is None, should raise before making any request."""
        import app.tracker.ship24_client as mod
        mod.config.SHIP24_API_KEY = None

        mock_post = mocker.patch("requests.post")

        with pytest.raises(Ship24Error, match="SHIP24_API_KEY is not configured"):
            create_tracker("TRACK123")

        mock_post.assert_not_called()

    def test_network_error_raises_ship24_error(self, mocker):
        """A network-level exception should be wrapped in Ship24Error."""
        mocker.patch(
            "requests.post",
            side_effect=requests.ConnectionError("Connection refused"),
        )

        with pytest.raises(Ship24Error, match="Network error"):
            create_tracker("TRACK123")
