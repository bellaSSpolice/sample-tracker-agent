"""HTTP endpoints: health check, manual triggers, shipment listing."""

import logging

from flask import Blueprint, jsonify, request

from app import config

logger = logging.getLogger(__name__)
bp = Blueprint("routes", __name__)


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/trigger/scan", methods=["POST"])
def trigger_scan():
    """Manually trigger an email scan. Requires TRIGGER_SECRET_KEY."""
    key = request.args.get("key", "")
    if key != config.TRIGGER_SECRET_KEY:
        return jsonify({"error": "Invalid key"}), 403

    from app.scanner.scan_job import run_email_scan
    try:
        run_email_scan()
        return jsonify({"status": "scan complete"})
    except Exception as e:
        logger.exception("Manual scan trigger failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/trigger/status_check", methods=["POST"])
def trigger_status_check():
    """Manually trigger a status check. Requires TRIGGER_SECRET_KEY."""
    key = request.args.get("key", "")
    if key != config.TRIGGER_SECRET_KEY:
        return jsonify({"error": "Invalid key"}), 403

    from app.tracker.status_checker import run_status_check
    try:
        run_status_check()
        return jsonify({"status": "status check complete"})
    except Exception as e:
        logger.exception("Manual status check trigger failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/shipments")
def list_shipments():
    """List all tracked shipments as JSON."""
    from app.db.connection import get_session
    from app.db.models import TrackedShipment

    session = get_session()
    try:
        shipments = session.query(TrackedShipment).order_by(
            TrackedShipment.created_at.desc()
        ).limit(200).all()

        result = []
        for s in shipments:
            result.append({
                "id": s.id,
                "tracking_number": s.tracking_number,
                "carrier": s.carrier,
                "tracking_url": s.tracking_url,
                "recipient_email": s.recipient_email,
                "email_subject": s.email_subject,
                "matched_client_id": str(s.matched_client_id) if s.matched_client_id else None,
                "matched_order_id": str(s.matched_order_id) if s.matched_order_id else None,
                "matched_sample_id": str(s.matched_sample_id) if s.matched_sample_id else None,
                "current_status": s.current_status,
                "status_detail": s.status_detail,
                "delivered_datetime": s.delivered_datetime.isoformat() if s.delivered_datetime else None,
                "delivery_draft_created": s.delivery_draft_created,
                "issue_draft_created": s.issue_draft_created,
                "detected_at": s.detected_at.isoformat() if s.detected_at else None,
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            })

        return jsonify({"shipments": result, "count": len(result)})
    finally:
        session.close()
