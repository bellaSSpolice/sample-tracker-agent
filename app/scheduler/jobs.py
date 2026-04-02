"""APScheduler job registration.

Registers two recurring jobs:
1. Email scan — every SCAN_INTERVAL_HOURS hours
2. Status check — every STATUS_CHECK_INTERVAL_HOURS hours, offset by 1 hour
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app import config

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler(app):
    """Initialize and start APScheduler with both jobs."""
    global _scheduler

    if _scheduler is not None:
        logger.warning("Scheduler already running, skipping duplicate init")
        return

    _scheduler = BackgroundScheduler()

    # Job 1: Email scan
    _scheduler.add_job(
        func=_run_email_scan_with_context,
        args=[app],
        trigger="interval",
        hours=config.SCAN_INTERVAL_HOURS,
        id="email_scan",
        name="Scan sent emails for tracking numbers",
        misfire_grace_time=600,  # 10 min grace if missed
    )

    # Job 2: Status check (offset by 1 hour)
    _scheduler.add_job(
        func=_run_status_check_with_context,
        args=[app],
        trigger="interval",
        hours=config.STATUS_CHECK_INTERVAL_HOURS,
        id="status_check",
        name="Check Ship24 for delivery updates",
        misfire_grace_time=600,
        # Start 1 hour after the scan job
        minutes=60,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: email scan every %dh, status check every %dh (offset 1h)",
        config.SCAN_INTERVAL_HOURS,
        config.STATUS_CHECK_INTERVAL_HOURS,
    )


def _run_email_scan_with_context(app):
    """Run email scan within Flask app context."""
    with app.app_context():
        from app.scanner.scan_job import run_email_scan
        run_email_scan()


def _run_status_check_with_context(app):
    """Run status check within Flask app context."""
    with app.app_context():
        from app.tracker.status_checker import run_status_check
        run_status_check()


def get_scheduler():
    """Return the scheduler instance (for testing/inspection)."""
    return _scheduler
