"""Scheduled job: scan sent emails for tracking numbers.

Runs every 2 hours. For each unprocessed sent email:
1. Parse for tracking numbers and URLs
2. Register each new tracking number with Ship24
3. Match to client (by email domain) and order (by tracking number or client)
4. Store in tracked_shipments table
5. Update orders/samples with tracking number
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db.connection import get_session
from app.db.models import EmailScanLog, Order, Sample, TrackedShipment
from app.gmail.auth import get_gmail_service
from app.gmail.reader import get_sent_emails
from app.matcher.client_matcher import match_client
from app.matcher.order_matcher import match_order
from app.scanner.email_parser import parse_email_for_tracking
from app.tracker.ship24_client import create_tracker, Ship24Error

logger = logging.getLogger(__name__)


def run_email_scan():
    """Main entry point for the email scanning job."""
    logger.info("=== Email scan job started ===")
    session = get_session()

    try:
        service = get_gmail_service()

        # Look back 48 hours to catch any emails we might have missed
        since = datetime.now(timezone.utc) - timedelta(hours=48)
        emails = get_sent_emails(service, since_datetime=since, max_results=100)

        total_tracking = 0
        for email_data in emails:
            msg_id = email_data["message_id"]

            # Skip already-scanned emails
            existing = session.query(EmailScanLog).filter(
                EmailScanLog.gmail_message_id == msg_id
            ).first()
            if existing:
                continue

            tracking_found = _process_email(session, email_data)
            total_tracking += tracking_found

            # Log this email as scanned
            scan_log = EmailScanLog(
                gmail_message_id=msg_id,
                email_subject=email_data.get("subject", "")[:1000],
                recipient_email=email_data.get("recipient_email", ""),
                sent_datetime=email_data.get("sent_datetime"),
                tracking_numbers_found=tracking_found,
            )
            session.add(scan_log)
            session.commit()

        logger.info(
            "=== Email scan complete: scanned %d emails, found %d tracking numbers ===",
            len(emails),
            total_tracking,
        )

    except Exception:
        logger.exception("Email scan job failed")
        session.rollback()
    finally:
        session.close()


def _process_email(session, email_data):
    """Process a single email for tracking numbers.

    Returns the count of new tracking numbers found.
    """
    subject = email_data.get("subject", "")
    body_text = email_data.get("body_text", "")
    body_html = email_data.get("body_html")
    msg_id = email_data["message_id"]
    recipient = email_data.get("recipient_email", "")

    tracking_items = parse_email_for_tracking(subject, body_text, body_html)
    if not tracking_items:
        return 0

    logger.info(
        "Found %d tracking number(s) in email to %s: %s",
        len(tracking_items),
        recipient,
        subject[:80],
    )

    count = 0
    for item in tracking_items:
        tracking_number = item["tracking_number"]
        carrier = item.get("carrier")
        tracking_url = item.get("tracking_url")

        # Skip if we already have this tracking number from this email
        existing = session.query(TrackedShipment).filter(
            TrackedShipment.tracking_number == tracking_number,
            TrackedShipment.source_email_id == msg_id,
        ).first()
        if existing:
            continue

        # Register with Ship24
        ship24_tracker_id = None
        courier_code = _carrier_to_ship24_code(carrier)
        try:
            tracker = create_tracker(tracking_number, courier_code)
            ship24_tracker_id = tracker.get("trackerId")
        except Ship24Error:
            logger.warning(
                "Failed to register tracking number %s with Ship24, will retry next cycle",
                tracking_number,
            )

        # Match to client
        client = match_client(recipient, session) if recipient else None

        # Match to order
        client_id = client.id if client else None
        match_result = match_order(tracking_number, client_id, session)
        matched_order = match_result.get("order")
        matched_sample = match_result.get("sample")

        # Create tracked shipment record
        shipment = TrackedShipment(
            tracking_number=tracking_number,
            carrier=carrier if carrier != "unknown" else None,
            tracking_url=tracking_url,
            ship24_tracker_id=ship24_tracker_id,
            source_email_id=msg_id,
            recipient_email=recipient,
            email_subject=subject[:1000],
            email_sent_datetime=email_data.get("sent_datetime"),
            matched_client_id=client.id if client else None,
            matched_order_id=matched_order.id if matched_order else None,
            matched_sample_id=matched_sample.id if matched_sample else None,
            current_status="pending",
        )
        session.add(shipment)

        # Update order/sample with tracking number
        _update_order_tracking(session, matched_order, matched_sample, tracking_number, carrier)

        session.commit()
        count += 1
        logger.info(
            "Stored tracking number %s (carrier=%s, client=%s, order=%s)",
            tracking_number,
            carrier,
            client.name if client else "unmatched",
            matched_order.id if matched_order else "unmatched",
        )

    return count


def _update_order_tracking(session, order, sample, tracking_number, carrier):
    """Write tracking number into the existing orders/samples table."""
    carrier_name = carrier if carrier and carrier != "unknown" else None

    if order:
        order.tracking_number = tracking_number
        if carrier_name:
            order.shipping_carrier = carrier_name
        session.add(order)

    if sample:
        sample.tracking_number = tracking_number
        if carrier_name:
            sample.shipping_carrier = carrier_name
        session.add(sample)


def _carrier_to_ship24_code(carrier):
    """Map our carrier name to Ship24's courier code (or None for auto-detect)."""
    mapping = {
        "USPS": "usps",
        "UPS": "ups",
        "FedEx": "fedex",
        "DHL": "dhl",
        "Amazon": "amazon",
    }
    return mapping.get(carrier)
