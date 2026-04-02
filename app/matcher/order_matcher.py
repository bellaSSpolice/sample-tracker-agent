from __future__ import annotations

"""Match a tracking number (and optional client) to an Order or Sample.

Priority:
    1. Direct match on orders.tracking_number
    2. Direct match on samples.tracking_number
    3. If client_id provided: find orders for that client in a matchable status
       (SAMPLING, IN_PRODUCTION, SHIPPED). Return only if exactly one matches.
    4. No match -> return all-None dict.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.config import MATCHABLE_ORDER_STATUSES
from app.db.models import Order, Sample

logger = logging.getLogger(__name__)


def match_order(
    tracking_number: str,
    client_id: uuid.UUID | None,
    session: Session,
) -> dict:
    """Try to link a tracking number to an existing Order or Sample.

    Args:
        tracking_number: The carrier tracking number to look up.
        client_id:       UUID of the matched client (may be None).
        session:         An active SQLAlchemy session.

    Returns:
        A dict with keys:
            order      - The matched Order (or None).
            sample     - The matched Sample (or None).
            match_type - One of "direct_order", "direct_sample",
                         "client_status", or "none".
    """
    no_match = {"order": None, "sample": None, "match_type": "none"}

    # --- 1. Direct match on orders.tracking_number ---
    order = (
        session.query(Order)
        .filter(Order.tracking_number == tracking_number)
        .first()
    )
    if order is not None:
        logger.info(
            "Direct order match: tracking=%s -> order_id=%s",
            tracking_number,
            order.id,
        )
        return {"order": order, "sample": None, "match_type": "direct_order"}

    # --- 2. Direct match on samples.tracking_number ---
    sample = (
        session.query(Sample)
        .filter(Sample.tracking_number == tracking_number)
        .first()
    )
    if sample is not None:
        # Also load the parent order if available.
        parent_order = None
        if sample.order_id:
            parent_order = (
                session.query(Order)
                .filter(Order.id == sample.order_id)
                .first()
            )
        logger.info(
            "Direct sample match: tracking=%s -> sample_id=%s (order_id=%s)",
            tracking_number,
            sample.id,
            sample.order_id,
        )
        return {"order": parent_order, "sample": sample, "match_type": "direct_sample"}

    # --- 3. Client + status fallback ---
    if client_id is not None:
        eligible_orders = (
            session.query(Order)
            .filter(
                Order.client_id == client_id,
                Order.production_status.in_(MATCHABLE_ORDER_STATUSES),
            )
            .all()
        )

        if len(eligible_orders) == 1:
            matched = eligible_orders[0]
            logger.info(
                "Client+status match: client_id=%s -> order_id=%s (status=%s)",
                client_id,
                matched.id,
                matched.production_status,
            )
            return {"order": matched, "sample": None, "match_type": "client_status"}

        if len(eligible_orders) > 1:
            logger.warning(
                "Ambiguous client+status match: client_id=%s has %d eligible orders. "
                "Not auto-matching.",
                client_id,
                len(eligible_orders),
            )
            return no_match

    # --- 4. No match ---
    logger.info("No match found for tracking=%s client_id=%s", tracking_number, client_id)
    return no_match
