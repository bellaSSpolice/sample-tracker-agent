"""Read sent emails from Gmail API.

Fetches emails from the SENT folder, extracts subject, recipient,
body (plain text and HTML), and metadata for tracking number scanning.
"""

import base64
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def get_sent_emails(service, since_datetime=None, max_results=100):
    """Fetch sent emails from Gmail, optionally filtered by date.

    Args:
        service: Authenticated Gmail API service object.
        since_datetime: Only fetch emails sent after this datetime (UTC).
        max_results: Maximum number of emails to return.

    Returns:
        List of dicts with keys: message_id, subject, recipient_email,
        sent_datetime, body_text, body_html.
    """
    query = "in:sent"
    if since_datetime:
        date_str = since_datetime.strftime("%Y/%m/%d")
        query += f" after:{date_str}"

    logger.info("Querying Gmail: %s (max %d)", query, max_results)

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    logger.info("Found %d sent emails", len(messages))

    emails = []
    for msg_stub in messages:
        msg_id = msg_stub["id"]
        email_data = _parse_message(service, msg_id)
        if email_data:
            emails.append(email_data)

    return emails


def _parse_message(service, message_id):
    """Fetch and parse a single Gmail message.

    Returns:
        Dict with message_id, subject, recipient_email, sent_datetime,
        body_text, body_html. Returns None on error.
    """
    try:
        msg = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
    except Exception:
        logger.exception("Failed to fetch message %s", message_id)
        return None

    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    subject = headers.get("subject", "")
    recipient = headers.get("to", "")
    date_str = headers.get("date", "")

    sent_datetime = None
    if date_str:
        try:
            sent_datetime = parsedate_to_datetime(date_str)
            if sent_datetime.tzinfo is None:
                sent_datetime = sent_datetime.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning("Could not parse date '%s' for message %s", date_str, message_id)

    body_text, body_html = _extract_body(msg.get("payload", {}))

    return {
        "message_id": message_id,
        "subject": subject,
        "recipient_email": _extract_email_address(recipient),
        "sent_datetime": sent_datetime,
        "body_text": body_text,
        "body_html": body_html,
    }


def _extract_body(payload):
    """Extract plain text and HTML body from a Gmail message payload.

    Handles both simple and multipart MIME structures.

    Returns:
        Tuple of (body_text, body_html).
    """
    body_text = ""
    body_html = ""

    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        body_text = _decode_body_data(payload.get("body", {}).get("data", ""))
    elif mime_type == "text/html":
        body_html = _decode_body_data(payload.get("body", {}).get("data", ""))

    # Multipart message — recurse into parts
    for part in payload.get("parts", []):
        part_text, part_html = _extract_body(part)
        if part_text:
            body_text = body_text or part_text
        if part_html:
            body_html = body_html or part_html

    return body_text, body_html


def _decode_body_data(data):
    """Decode base64url-encoded Gmail body data to string."""
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_email_address(to_header):
    """Extract bare email address from a To header.

    Handles formats like:
        - 'user@example.com'
        - 'John Doe <user@example.com>'
        - 'user@example.com, other@example.com' (returns first)
    """
    if not to_header:
        return ""

    # Take first recipient if multiple
    first = to_header.split(",")[0].strip()

    # Extract from angle brackets if present
    if "<" in first and ">" in first:
        start = first.index("<") + 1
        end = first.index(">")
        return first[start:end].strip().lower()

    return first.strip().lower()
