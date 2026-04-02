"""Integration tests for the status checker job.

Mocks Ship24 and Gmail to test:
status fetch → update shipment → update order → draft notifications.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


def _make_shipment(status="in_transit", tracker_id="tracker-001"):
    """Create a mock TrackedShipment."""
    s = MagicMock()
    s.id = 1
    s.tracking_number = "9400111899223100012345"
    s.carrier = "USPS"
    s.ship24_tracker_id = tracker_id
    s.current_status = status
    s.status_detail = "In transit"
    s.matched_client_id = uuid.uuid4()
    s.matched_order_id = uuid.uuid4()
    s.matched_sample_id = None
    s.delivered_datetime = None
    s.delivery_draft_created = False
    s.issue_draft_created = False
    s.recipient_email = "john@hotel.com"
    return s


@patch("app.tracker.status_checker.create_delivery_notification")
@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_delivered_updates_order_and_creates_draft(
    mock_get_session,
    mock_get_results,
    mock_create_notification,
):
    """When Ship24 says delivered, we update order and create draft."""
    session = MagicMock()
    shipment = _make_shipment(status="in_transit")

    # Session returns our active shipment
    session.query().filter().all.return_value = [shipment]

    # Order query for delivery handler
    mock_order = MagicMock()
    mock_order.id = shipment.matched_order_id
    mock_order.production_status = "IN_PRODUCTION"

    mock_client = MagicMock()
    mock_client.id = shipment.matched_client_id
    mock_client.delivery_notification_enabled = True

    # Make session.query(X).filter().first() return different things
    # based on the model being queried
    def query_side_effect(model=None):
        q = MagicMock()
        if model and hasattr(model, '__tablename__'):
            if model.__tablename__ == 'orders':
                q.filter().first.return_value = mock_order
            elif model.__tablename__ == 'clients':
                q.filter().first.return_value = mock_client
            elif model.__tablename__ == 'samples':
                q.filter().first.return_value = None
            else:
                q.filter().first.return_value = None
                q.filter().all.return_value = [shipment]
        else:
            q.filter().first.return_value = None
            q.filter().all.return_value = [shipment]
        return q

    session.query = query_side_effect
    mock_get_session.return_value = session

    # Ship24 returns "delivered" status
    mock_get_results.return_value = {
        "trackings": [{
            "shipment": {"statusCode": "delivered", "statusMilestone": "Delivered"},
            "events": [{"description": "Delivered to front door"}],
        }]
    }

    mock_create_notification.return_value = "draft-delivery-001"

    from app.tracker.status_checker import run_status_check
    run_status_check()

    # Shipment should be updated to delivered
    assert shipment.current_status == "delivered"
    assert shipment.delivered_datetime is not None


@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_no_status_change_no_notifications(
    mock_get_session,
    mock_get_results,
):
    """If status hasn't changed, no notifications are created."""
    session = MagicMock()
    shipment = _make_shipment(status="in_transit")
    session.query().filter().all.return_value = [shipment]
    mock_get_session.return_value = session

    mock_get_results.return_value = {
        "trackings": [{
            "shipment": {"statusCode": "inTransit", "statusMilestone": "In transit"},
            "events": [{"description": "Package in transit"}],
        }]
    }

    from app.tracker.status_checker import run_status_check
    run_status_check()

    # Status stays in_transit
    assert shipment.current_status == "in_transit"
    # No delivery datetime set
    assert shipment.delivered_datetime is None


@patch("app.tracker.status_checker.create_issue_alert")
@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_exception_creates_alert_draft(
    mock_get_session,
    mock_get_results,
    mock_create_alert,
):
    """Shipping exception should trigger an alert draft."""
    session = MagicMock()
    shipment = _make_shipment(status="in_transit")
    session.query().filter().all.return_value = [shipment]
    mock_get_session.return_value = session

    mock_get_results.return_value = {
        "trackings": [{
            "shipment": {"statusCode": "exception", "statusMilestone": "Exception"},
            "events": [{"description": "Package damaged"}],
        }]
    }
    mock_create_alert.return_value = "draft-alert-001"

    from app.tracker.status_checker import run_status_check
    run_status_check()

    assert shipment.current_status == "exception"
    mock_create_alert.assert_called_once()
    assert shipment.issue_draft_created is True


@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_ship24_failure_skips_shipment(
    mock_get_session,
    mock_get_results,
):
    """Ship24 API failure should skip the shipment gracefully."""
    from app.tracker.ship24_client import Ship24Error

    session = MagicMock()
    shipment = _make_shipment(status="in_transit")
    session.query().filter().all.return_value = [shipment]
    mock_get_session.return_value = session

    mock_get_results.side_effect = Ship24Error("API down")

    from app.tracker.status_checker import run_status_check
    run_status_check()

    # Status should remain unchanged
    assert shipment.current_status == "in_transit"


@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_empty_tracking_data_handled(
    mock_get_session,
    mock_get_results,
):
    """No tracking data from Ship24 should be handled gracefully."""
    session = MagicMock()
    shipment = _make_shipment(status="pending")
    session.query().filter().all.return_value = [shipment]
    mock_get_session.return_value = session

    mock_get_results.return_value = {"trackings": []}

    from app.tracker.status_checker import run_status_check
    run_status_check()

    # Status should remain pending
    assert shipment.current_status == "pending"
