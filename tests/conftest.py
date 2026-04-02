"""Shared test fixtures for the Sample Tracker Agent test suite."""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Set test environment before any app imports
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SHIP24_API_KEY", "test-api-key")
os.environ.setdefault("GMAIL_ADDRESS", "test@sleepysaturday.com")
os.environ.setdefault("TRIGGER_SECRET_KEY", "test-trigger-key")


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_gmail_service():
    """Create a mock Gmail API service."""
    service = MagicMock()
    return service


@pytest.fixture
def sample_client():
    """Create a mock Client object."""
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = "Windsor Court Hotel"
    client.contact_email = "imarciante@windsorcourthotel.com"
    client.delivery_notification_enabled = True
    return client


@pytest.fixture
def sample_order():
    """Create a mock Order object."""
    order = MagicMock()
    order.id = uuid.uuid4()
    order.tracking_number = None
    order.shipping_carrier = None
    order.production_status = "IN_PRODUCTION"
    order.delivered_date = None
    order.client_id = uuid.uuid4()
    return order


@pytest.fixture
def sample_sample():
    """Create a mock Sample object."""
    sample = MagicMock()
    sample.id = uuid.uuid4()
    sample.tracking_number = None
    sample.shipping_carrier = None
    sample.status = "IN_PRODUCTION"
    sample.delivered_date = None
    sample.order_id = uuid.uuid4()
    return sample


@pytest.fixture
def sample_shipment():
    """Create a mock TrackedShipment object."""
    shipment = MagicMock()
    shipment.id = 1
    shipment.tracking_number = "9400111899223100012345"
    shipment.carrier = "USPS"
    shipment.tracking_url = None
    shipment.ship24_tracker_id = "tracker-abc-123"
    shipment.source_email_id = "msg-001"
    shipment.recipient_email = "imarciante@windsorcourthotel.com"
    shipment.email_subject = "Your order has shipped!"
    shipment.matched_client_id = uuid.uuid4()
    shipment.matched_order_id = uuid.uuid4()
    shipment.matched_sample_id = None
    shipment.current_status = "in_transit"
    shipment.status_detail = "In transit to destination"
    shipment.delivered_datetime = None
    shipment.delivery_draft_created = False
    shipment.issue_draft_created = False
    return shipment
