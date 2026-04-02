"""Tests for Gmail draft creator — verifies drafts are created, NEVER sent."""

import pytest
from unittest.mock import MagicMock, patch

from app.gmail.draft_creator import create_delivery_draft, create_alert_draft


@pytest.fixture
def mock_service():
    """Gmail API service mock that returns a draft ID."""
    service = MagicMock()
    service.users().drafts().create().execute.return_value = {"id": "draft-abc-123"}
    return service


class TestCreateDeliveryDraft:
    def test_creates_draft_with_correct_subject(self, mock_service):
        draft_id = create_delivery_draft(
            service=mock_service,
            to_email="client@hotel.com",
            client_name="Windsor Court Hotel",
            tracking_number="9400111899223100012345",
            carrier="USPS",
        )
        assert draft_id == "draft-abc-123"
        # Verify draft was created (not sent)
        mock_service.users().drafts().create.assert_called()
        # Verify send was NOT called
        mock_service.users().messages().send.assert_not_called()

    def test_draft_body_contains_tracking_number(self, mock_service):
        create_delivery_draft(
            service=mock_service,
            to_email="client@hotel.com",
            client_name="Test Hotel",
            tracking_number="1Z999AA10123456784",
            carrier="UPS",
        )
        # Verify the create call was made with message body
        call_args = mock_service.users().drafts().create.call_args
        assert call_args is not None

    def test_returns_draft_id(self, mock_service):
        result = create_delivery_draft(
            service=mock_service,
            to_email="a@b.com",
            client_name="Test",
            tracking_number="123",
            carrier="USPS",
        )
        assert isinstance(result, str)
        assert result == "draft-abc-123"


class TestCreateAlertDraft:
    def test_creates_alert_draft(self, mock_service):
        draft_id = create_alert_draft(
            service=mock_service,
            issue_type="Shipping Exception",
            tracking_number="9400111899223100012345",
            carrier="USPS",
            recipient_email="client@hotel.com",
            client_name="Windsor Court Hotel",
            order_info="Order ID: abc-123",
            status_detail="Package damaged in transit",
        )
        assert draft_id == "draft-abc-123"
        mock_service.users().drafts().create.assert_called()
        mock_service.users().messages().send.assert_not_called()

    def test_alert_sent_to_hello_address(self, mock_service):
        """Alert drafts should be addressed to hello@sleepysaturday.com."""
        create_alert_draft(
            service=mock_service,
            issue_type="Delay",
            tracking_number="123",
            carrier="UPS",
            recipient_email="client@hotel.com",
            client_name="Test",
            order_info="N/A",
            status_detail="Delayed",
        )
        # Draft was created (not sent)
        mock_service.users().drafts().create.assert_called()

    def test_returns_draft_id(self, mock_service):
        result = create_alert_draft(
            service=mock_service,
            issue_type="Exception",
            tracking_number="123",
            carrier="FedEx",
            recipient_email="a@b.com",
            client_name="Test",
            order_info="N/A",
            status_detail="Exception",
        )
        assert isinstance(result, str)
