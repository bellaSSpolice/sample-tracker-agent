"""Create a SHIPPING ALERT notification draft in Gmail.

IMPORTANT: This module NEVER auto-sends emails.
It creates a Gmail draft addressed to hello@sleepysaturday.com so
the team can review the issue and decide how to respond.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import NotificationLog, TrackedShipment
from app.gmail.auth import get_gmail_service
from app.gmail.draft_creator import create_alert_draft

logger = logging.getLogger(__name__)


def create_issue_alert(
    shipment: TrackedShipment,
    issue_type: str,
    session: Session,
) -> str:
    """Create a Gmail draft alerting the team about a shipping issue.

    Args:
        shipment:   The TrackedShipment that has an issue.
        issue_type: Short label for the problem (e.g. "Stalled",
                    "Exception", "Returned to Sender").
        session:    An active SQLAlchemy session.

    Returns:
        The Gmail draft ID.
    """
    # --- Build order info string from matched data ---
    order_info_parts = []
    if shipment.matched_order_id:
        order_info_parts.append(f"Order ID: {shipment.matched_order_id}")
    if shipment.matched_sample_id:
        order_info_parts.append(f"Sample ID: {shipment.matched_sample_id}")
    order_info = " | ".join(order_info_parts) if order_info_parts else "No matched order/sample"

    # --- Derive client name from matched_client_id (if we have it) ---
    client_name = "Unknown"
    if shipment.matched_client_id:
        from app.db.models import Client

        client = (
            session.query(Client)
            .filter(Client.id == shipment.matched_client_id)
            .first()
        )
        if client:
            client_name = client.name or "Unknown"

    # --- Build and create the draft ---
    service = get_gmail_service()

    draft_id = create_alert_draft(
        service=service,
        issue_type=issue_type,
        tracking_number=shipment.tracking_number,
        carrier=shipment.carrier or "Unknown carrier",
        recipient_email=shipment.recipient_email or "Unknown",
        client_name=client_name,
        order_info=order_info,
        status_detail=shipment.status_detail or "No detail available",
    )

    # --- Log the notification ---
    log_entry = NotificationLog(
        id=uuid.uuid4(),
        order_id=shipment.matched_order_id,
        sample_id=shipment.matched_sample_id,
        client_id=shipment.matched_client_id,
        notification_type="SHIPPING_ALERT",
        status="DRAFTED",
    )
    session.add(log_entry)
    session.commit()

    logger.info(
        "Alert draft created (draft_id=%s) issue_type=%s tracking=%s",
        draft_id,
        issue_type,
        shipment.tracking_number,
    )

    return draft_id
