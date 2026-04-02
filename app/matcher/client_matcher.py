from __future__ import annotations

"""Match a shipping recipient email to a Client in the database.

Strategy:
    1. Extract the domain from the recipient email.
    2. Skip common personal email domains (they won't match a business client).
    3. Query the clients table for any client whose contact_email shares the
       same domain.
    4. Return the match (or None).
"""

import logging

from sqlalchemy.orm import Session

from app.db.models import Client

logger = logging.getLogger(__name__)

# Personal / free email providers -- these will never match a business client.
PERSONAL_EMAIL_DOMAINS = frozenset({
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
})


def _extract_domain(email: str) -> str | None:
    """Return the full domain portion after '@', lowercased.

    Returns None if the email doesn't contain exactly one '@'.
    """
    if not email or "@" not in email:
        return None
    parts = email.strip().lower().split("@")
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[1]


def match_client(recipient_email: str, session: Session) -> Client | None:
    """Find a Client whose contact_email domain matches *recipient_email*.

    Args:
        recipient_email: The email address the shipment was sent to
                         (e.g. "john@windsorcourthotel.com").
        session:         An active SQLAlchemy session.

    Returns:
        The matched Client, or None if no match was found.
    """
    domain = _extract_domain(recipient_email)
    if domain is None:
        logger.warning("Could not extract domain from email: %s", recipient_email)
        return None

    if domain in PERSONAL_EMAIL_DOMAINS:
        logger.info(
            "Skipping personal email domain '%s' -- won't match a business client.",
            domain,
        )
        return None

    # Find all clients whose contact_email ends with '@<domain>'.
    # Using LIKE with a pattern anchored to '@domain' is simple and safe here
    # because the domain string comes from a real email, not user input.
    like_pattern = f"%@{domain}"
    matches = (
        session.query(Client)
        .filter(Client.contact_email.ilike(like_pattern))
        .all()
    )

    if not matches:
        logger.info("No client found for domain '%s'.", domain)
        return None

    if len(matches) > 1:
        logger.warning(
            "Multiple clients matched domain '%s': %s. Returning the first.",
            domain,
            [str(c.id) for c in matches],
        )

    return matches[0]
