"""Integration tests for the email scan job.

Mocks Gmail API and Ship24 to test the full scan flow:
email fetch → parse → Ship24 register → match → store.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_gmail_emails():
    """Simulated emails returned by the Gmail reader."""
    return [
        {
            "message_id": "msg-001",
            "subject": "Your order has shipped!",
            "recipient_email": "john@windsorcourthotel.com",
            "sent_datetime": datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc),
            "body_text": "Your USPS tracking number is 9400111899223100012345. Thanks!",
            "body_html": None,
        },
        {
            "message_id": "msg-002",
            "subject": "Meeting notes",
            "recipient_email": "team@example.com",
            "sent_datetime": datetime(2024, 3, 15, 11, 0, tzinfo=timezone.utc),
            "body_text": "Here are the notes from today's meeting.",
            "body_html": None,
        },
    ]


@patch("app.scanner.scan_job.get_gmail_service")
@patch("app.scanner.scan_job.get_sent_emails")
@patch("app.scanner.scan_job.create_tracker")
@patch("app.scanner.scan_job.match_client")
@patch("app.scanner.scan_job.match_order")
@patch("app.scanner.scan_job.get_session")
def test_scan_finds_tracking_in_email(
    mock_get_session,
    mock_match_order,
    mock_match_client,
    mock_create_tracker,
    mock_get_sent_emails,
    mock_get_gmail_service,
    mock_gmail_emails,
    sample_client,
    sample_order,
):
    """Full scan flow: one email has a tracking number, one doesn't."""
    # Setup mocks
    session = MagicMock()
    # email_scan_log query returns None (not yet scanned)
    session.query().filter().first.return_value = None
    mock_get_session.return_value = session

    mock_get_gmail_service.return_value = MagicMock()
    mock_get_sent_emails.return_value = mock_gmail_emails
    mock_create_tracker.return_value = {"trackerId": "tracker-001"}
    mock_match_client.return_value = sample_client
    mock_match_order.return_value = {
        "order": sample_order,
        "sample": None,
        "match_type": "client_status",
    }

    from app.scanner.scan_job import run_email_scan
    run_email_scan()

    # Ship24 tracker should be created for the tracking number
    mock_create_tracker.assert_called_once()
    call_args = mock_create_tracker.call_args
    assert call_args[0][0] == "9400111899223100012345"

    # Client matching should be called for the email with tracking
    mock_match_client.assert_called()

    # Session should have had items added (shipment + scan logs)
    assert session.add.called
    assert session.commit.called


@patch("app.scanner.scan_job.get_gmail_service")
@patch("app.scanner.scan_job.get_sent_emails")
@patch("app.scanner.scan_job.get_session")
def test_scan_skips_already_scanned_emails(
    mock_get_session,
    mock_get_sent_emails,
    mock_get_gmail_service,
    mock_gmail_emails,
):
    """Emails already in email_scan_log should be skipped."""
    session = MagicMock()
    # Return a non-None value to indicate email was already scanned
    existing_log = MagicMock()
    session.query().filter().first.return_value = existing_log
    mock_get_session.return_value = session

    mock_get_gmail_service.return_value = MagicMock()
    mock_get_sent_emails.return_value = mock_gmail_emails

    from app.scanner.scan_job import run_email_scan
    run_email_scan()

    # No new tracking should be processed since all emails are "already scanned"
    # Only the scan log queries should have been made
    assert session.commit.call_count == 0


@patch("app.scanner.scan_job.get_gmail_service")
@patch("app.scanner.scan_job.get_sent_emails")
@patch("app.scanner.scan_job.get_session")
def test_scan_handles_no_emails(
    mock_get_session,
    mock_get_sent_emails,
    mock_get_gmail_service,
):
    """Empty inbox should complete without errors."""
    session = MagicMock()
    mock_get_session.return_value = session
    mock_get_gmail_service.return_value = MagicMock()
    mock_get_sent_emails.return_value = []

    from app.scanner.scan_job import run_email_scan
    run_email_scan()

    # Should complete gracefully with no errors
    assert not session.add.called


@patch("app.scanner.scan_job.get_gmail_service")
@patch("app.scanner.scan_job.get_sent_emails")
@patch("app.scanner.scan_job.create_tracker")
@patch("app.scanner.scan_job.match_client")
@patch("app.scanner.scan_job.match_order")
@patch("app.scanner.scan_job.get_session")
def test_scan_handles_ship24_failure(
    mock_get_session,
    mock_match_order,
    mock_match_client,
    mock_create_tracker,
    mock_get_sent_emails,
    mock_get_gmail_service,
    mock_gmail_emails,
):
    """Ship24 failure should not crash the scan — shipment stored without tracker ID."""
    from app.tracker.ship24_client import Ship24Error

    session = MagicMock()
    session.query().filter().first.return_value = None
    mock_get_session.return_value = session

    mock_get_gmail_service.return_value = MagicMock()
    mock_get_sent_emails.return_value = [mock_gmail_emails[0]]  # Only the email with tracking
    mock_create_tracker.side_effect = Ship24Error("API down")
    mock_match_client.return_value = None
    mock_match_order.return_value = {"order": None, "sample": None, "match_type": "none"}

    from app.scanner.scan_job import run_email_scan
    run_email_scan()

    # Should still store the shipment (without ship24_tracker_id)
    assert session.add.called
    assert session.commit.called
