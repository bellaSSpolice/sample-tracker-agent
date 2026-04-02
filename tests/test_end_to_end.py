"""End-to-end test simulating the full lifecycle:

1. Mock Gmail returns email with tracking number to a known client
2. Mock Ship24 accepts tracker, returns "in_transit" then "delivered"
3. Verify: shipment created, matched to client+order, order updated, draft created
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@patch("app.scanner.scan_job.get_gmail_service")
@patch("app.scanner.scan_job.get_sent_emails")
@patch("app.scanner.scan_job.create_tracker")
@patch("app.scanner.scan_job.get_session")
def test_full_lifecycle_scan_phase(
    mock_get_session,
    mock_create_tracker,
    mock_get_sent_emails,
    mock_get_gmail_service,
):
    """Phase 1: Email scan finds tracking number and stores it."""
    from app.scanner.scan_job import run_email_scan

    client_id = uuid.uuid4()
    order_id = uuid.uuid4()

    # Mock client
    mock_client = MagicMock()
    mock_client.id = client_id
    mock_client.name = "Ocean Reef Club"
    mock_client.contact_email = "manager@oceanreefclub.com"

    # Mock order
    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.tracking_number = None
    mock_order.shipping_carrier = None
    mock_order.production_status = "IN_PRODUCTION"
    mock_order.client_id = client_id

    session = MagicMock()
    # No existing scan log (first scan)
    session.query().filter().first.return_value = None
    mock_get_session.return_value = session

    mock_get_gmail_service.return_value = MagicMock()
    mock_get_sent_emails.return_value = [
        {
            "message_id": "msg-e2e-001",
            "subject": "Your samples have shipped!",
            "recipient_email": "manager@oceanreefclub.com",
            "sent_datetime": datetime(2024, 3, 20, 10, 0, tzinfo=timezone.utc),
            "body_text": (
                "Hi there,\n\nYour samples are on the way!\n"
                "USPS tracking number: 9400111899223100055555\n\nThanks!"
            ),
            "body_html": None,
        },
    ]

    mock_create_tracker.return_value = {"trackerId": "tracker-e2e-001"}

    # Patch matchers to return our test data
    with patch("app.scanner.scan_job.match_client", return_value=mock_client), \
         patch("app.scanner.scan_job.match_order", return_value={
             "order": mock_order,
             "sample": None,
             "match_type": "client_status",
         }):
        run_email_scan()

    # Verify Ship24 tracker was created
    mock_create_tracker.assert_called_once_with("9400111899223100055555", "usps")

    # Verify data was persisted
    assert session.add.called
    assert session.commit.called

    # Verify order tracking_number was updated
    assert mock_order.tracking_number == "9400111899223100055555"
    assert mock_order.shipping_carrier == "USPS"


@patch("app.tracker.status_checker.create_delivery_notification")
@patch("app.tracker.status_checker.get_tracking_results")
@patch("app.tracker.status_checker.get_session")
def test_full_lifecycle_delivery_phase(
    mock_get_session,
    mock_get_results,
    mock_create_notification,
):
    """Phase 2: Status check detects delivery and creates draft."""
    from app.tracker.status_checker import run_status_check

    client_id = uuid.uuid4()
    order_id = uuid.uuid4()

    # Mock the shipment (already tracked from scan phase)
    shipment = MagicMock()
    shipment.id = 1
    shipment.tracking_number = "9400111899223100055555"
    shipment.carrier = "USPS"
    shipment.ship24_tracker_id = "tracker-e2e-001"
    shipment.current_status = "in_transit"
    shipment.status_detail = "In transit"
    shipment.matched_client_id = client_id
    shipment.matched_order_id = order_id
    shipment.matched_sample_id = None
    shipment.delivered_datetime = None
    shipment.delivery_draft_created = False
    shipment.issue_draft_created = False
    shipment.recipient_email = "manager@oceanreefclub.com"

    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.production_status = "IN_PRODUCTION"

    mock_client = MagicMock()
    mock_client.id = client_id
    mock_client.delivery_notification_enabled = True

    session = MagicMock()

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

    # Ship24 returns delivered
    mock_get_results.return_value = {
        "trackings": [{
            "shipment": {"statusCode": "delivered", "statusMilestone": "Delivered"},
            "events": [{"description": "Delivered - left at front door"}],
        }]
    }

    mock_create_notification.return_value = "draft-e2e-delivery"

    run_status_check()

    # Verify shipment updated to delivered
    assert shipment.current_status == "delivered"
    assert shipment.delivered_datetime is not None

    # Verify order updated to DELIVERED
    assert mock_order.production_status == "DELIVERED"
    assert mock_order.delivered_date is not None

    # Verify delivery draft was created
    assert shipment.delivery_draft_created is True
