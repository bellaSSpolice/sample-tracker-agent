"""Scheduled job: check Ship24 for delivery status updates.

Runs every 2 hours (offset by 1 hour from email scan).
For each active (non-delivered) shipment:
1. Query Ship24 for latest status
2. Update tracked_shipments table
3. If delivered: update order status, create delivery draft
4. If exception/delay: create alert draft
"""

import logging
from datetime import datetime, timezone

from app.db.connection import get_session
from app.db.models import Client, Order, Sample, TrackedShipment
from app import config
from app.notifications.delivery_notifier import create_delivery_notification
from app.notifications.alert_notifier import create_issue_alert
from app.tracker.ship24_client import get_tracking_results, normalize_status, Ship24Error

logger = logging.getLogger(__name__)


def run_status_check():
    """Main entry point for the status checking job."""
    logger.info("=== Status check job started ===")
    session = get_session()

    try:
        # Get all active (non-delivered) shipments that have a Ship24 tracker
        active_shipments = session.query(TrackedShipment).filter(
            TrackedShipment.current_status != "delivered",
            TrackedShipment.ship24_tracker_id.isnot(None),
        ).all()

        logger.info("Checking status for %d active shipments", len(active_shipments))

        for shipment in active_shipments:
            _check_shipment(session, shipment)

        logger.info("=== Status check complete ===")

    except Exception:
        logger.exception("Status check job failed")
        session.rollback()
    finally:
        session.close()


def _check_shipment(session, shipment):
    """Check and update status for a single shipment."""
    try:
        results = get_tracking_results(shipment.ship24_tracker_id)
    except Ship24Error:
        logger.warning(
            "Failed to get status for %s (tracker=%s), will retry next cycle",
            shipment.tracking_number,
            shipment.ship24_tracker_id,
        )
        return

    # Extract status from Ship24 results
    trackings = results.get("trackings", [])
    if not trackings:
        logger.debug("No tracking data yet for %s", shipment.tracking_number)
        return

    latest = trackings[0]
    events = latest.get("events", [])
    ship24_status = latest.get("shipment", {}).get("statusCode", "")
    status_detail = latest.get("shipment", {}).get("statusMilestone", "")

    if events:
        latest_event = events[0]
        status_detail = latest_event.get("description", status_detail)

    new_status = normalize_status(ship24_status)
    old_status = shipment.current_status

    # Update shipment record
    shipment.current_status = new_status
    shipment.status_detail = status_detail
    shipment.last_checked_at = datetime.now(timezone.utc)
    shipment.updated_at = datetime.now(timezone.utc)

    if new_status != old_status:
        logger.info(
            "Status changed for %s: %s → %s (%s)",
            shipment.tracking_number,
            old_status,
            new_status,
            status_detail,
        )

    # Handle delivered status
    if new_status == "delivered" and old_status != "delivered":
        _handle_delivery(session, shipment)

    # Handle exception/delay
    if new_status == "exception" and not shipment.issue_draft_created:
        _handle_exception(session, shipment, status_detail)

    session.add(shipment)
    session.commit()


def _handle_delivery(session, shipment):
    """Handle a newly delivered shipment: update order + create draft."""
    now = datetime.now(timezone.utc)
    shipment.delivered_datetime = now

    # Update order status to DELIVERED (only if in an eligible status)
    if shipment.matched_order_id:
        order = session.query(Order).filter(Order.id == shipment.matched_order_id).first()
        if order and order.production_status in config.MATCHABLE_ORDER_STATUSES:
            order.production_status = "DELIVERED"
            order.delivered_date = now
            session.add(order)
            logger.info(
                "Updated order %s to DELIVERED",
                order.id,
            )

    # Update sample status if matched
    if shipment.matched_sample_id:
        sample = session.query(Sample).filter(Sample.id == shipment.matched_sample_id).first()
        if sample:
            sample.status = "DELIVERED"
            sample.delivered_date = now
            session.add(sample)

    # Create delivery notification draft
    if not shipment.delivery_draft_created and shipment.matched_client_id:
        client = session.query(Client).filter(Client.id == shipment.matched_client_id).first()
        order = None
        if shipment.matched_order_id:
            order = session.query(Order).filter(Order.id == shipment.matched_order_id).first()

        if client:
            try:
                draft_id = create_delivery_notification(shipment, client, order, session)
                if draft_id:
                    shipment.delivery_draft_created = True
                    logger.info("Created delivery draft for %s", shipment.tracking_number)
            except Exception:
                logger.exception(
                    "Failed to create delivery draft for %s",
                    shipment.tracking_number,
                )


def _handle_exception(session, shipment, status_detail):
    """Handle a shipping exception: create alert draft."""
    try:
        draft_id = create_issue_alert(shipment, "Shipping Exception", session)
        if draft_id:
            shipment.issue_draft_created = True
            logger.info("Created alert draft for %s", shipment.tracking_number)
    except Exception:
        logger.exception(
            "Failed to create alert draft for %s",
            shipment.tracking_number,
        )
