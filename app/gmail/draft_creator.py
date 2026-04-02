"""Create DRAFT emails via the Gmail API.

IMPORTANT: This module NEVER auto-sends emails.
Every message is created as a draft that a human must review and
manually send from the Gmail UI.
"""

import base64
import logging
from email.mime.text import MIMEText

from app.config import GMAIL_ADDRESS

logger = logging.getLogger(__name__)


def _build_mime_message(to, subject, body_text):
    """Build a MIMEText message and return the raw base64url-encoded string."""
    message = MIMEText(body_text)
    message["to"] = to
    message["from"] = GMAIL_ADDRESS
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw


def _create_draft(service, to, subject, body_text):
    """Create a Gmail draft and return its ID.

    This is the single internal function that actually calls the API.
    It NEVER sends -- only creates a draft.
    """
    raw = _build_mime_message(to, subject, body_text)
    draft_body = {"message": {"raw": raw}}

    draft = (
        service.users()
        .drafts()
        .create(userId="me", body=draft_body)
        .execute()
    )
    draft_id = draft["id"]
    logger.info("Draft created (id=%s) to=%s subject=%s", draft_id, to, subject)
    return draft_id


# ------------------------------------------------------------------
# Public helpers
# ------------------------------------------------------------------


def create_delivery_draft(service, to_email, client_name, tracking_number, carrier):
    """Create a draft confirming delivery and asking for feedback.

    Args:
        service:         Authenticated Gmail API service object.
        to_email:        Recipient email address.
        client_name:     Human-readable client / brand name.
        tracking_number: The shipment tracking number.
        carrier:         Carrier name (e.g. "UPS", "FedEx").

    Returns:
        The Gmail draft ID (str).
    """
    subject = f"Your {client_name} samples have been delivered!"

    body = (
        f"Hi there,\n"
        f"\n"
        f"Great news -- your samples from {client_name} have been delivered!\n"
        f"\n"
        f"Tracking number: {tracking_number}\n"
        f"Carrier: {carrier}\n"
        f"\n"
        f"Could you take a moment to let us know how everything looks? "
        f"We'd love to hear your feedback.\n"
        f"\n"
        f"Thanks,\n"
        f"Sleepy Saturday"
    )

    return _create_draft(service, to_email, subject, body)


def create_alert_draft(
    service,
    issue_type,
    tracking_number,
    carrier,
    recipient_email,
    client_name,
    order_info,
    status_detail,
):
    """Create a draft alerting the Sleepy Saturday team of a shipping issue.

    The draft is addressed to hello@sleepysaturday.com so a team member
    can review it and decide how to respond.

    Args:
        service:         Authenticated Gmail API service object.
        issue_type:      Short label for the problem (e.g. "Stalled",
                         "Exception", "Returned to Sender").
        tracking_number: The shipment tracking number.
        carrier:         Carrier name.
        recipient_email: Who the shipment was going to.
        client_name:     Client / brand name associated with the order.
        order_info:      Free-text order reference (order ID, PO number, etc.).
        status_detail:   Latest status message from the carrier.

    Returns:
        The Gmail draft ID (str).
    """
    to = "hello@sleepysaturday.com"
    subject = f"[Sample Tracker Alert] {issue_type} -- {tracking_number}"

    body = (
        f"Shipping issue detected by Sample Tracker.\n"
        f"\n"
        f"Issue type:      {issue_type}\n"
        f"Tracking number: {tracking_number}\n"
        f"Carrier:         {carrier}\n"
        f"Client:          {client_name}\n"
        f"Recipient:       {recipient_email}\n"
        f"Order info:      {order_info}\n"
        f"Latest status:   {status_detail}\n"
        f"\n"
        f"Please review and take any necessary action.\n"
    )

    return _create_draft(service, to, subject, body)
