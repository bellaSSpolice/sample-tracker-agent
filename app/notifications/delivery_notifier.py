from __future__ import annotations

"""Create a DELIVERY notification draft in Gmail.

IMPORTANT: This module NEVER auto-sends emails.
It creates a Gmail draft and logs the action to notification_logs.
A human must review and manually send the draft from the Gmail UI.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Client, NotificationLog, Order, TrackedShipment
from app.gmail.auth import get_gmail_service
from app.gmail.draft_creator import create_delivery_draft

logger = logging.getLogger(__name__)


def create_delivery_notification(
    shipment: TrackedShipment,
    client: Client,
    order: Order | None,
    session: Session,
) -> str | None:
    """Create a Gmail draft notifying the client that their shipment was delivered.

    Args:
        shipment: The TrackedShipment that was delivered.
        client:   The matched Client who should be notified.
        order:    The matched Order (may be None if only a sample matched).
        session:  An active SQLAlchemy session.

    Returns:
        The Gmail draft ID if a draft was created, or None if skipped.
    """
    # --- Guard: check client preference ---
    if not client.delivery_notification_enabled:
        logger.info(
            "Delivery notifications disabled for client %s (%s). Skipping.",
            client.id,
            client.name,
        )
        return None

    # --- Build and create the draft ---
    service = get_gmail_service()

    draft_id = create_delivery_draft(
        service=service,
        to_email=client.contact_email,
        client_name=client.name or "your brand",
        tracking_number=shipment.tracking_number,
        carrier=shipment.carrier or "Unknown carrier",
    )

    # --- Log the notification ---
    log_entry = NotificationLog(
        id=uuid.uuid4(),
        order_id=order.id if order else None,
        sample_id=shipment.matched_sample_id,
        client_id=client.id,
        notification_type="DELIVERY",
        status="DRAFTED",
    )
    session.add(log_entry)
    session.commit()

    logger.info(
        "Delivery draft created (draft_id=%s) for client %s, shipment tracking=%s",
        draft_id,
        client.id,
        shipment.tracking_number,
    )

    return draft_id
