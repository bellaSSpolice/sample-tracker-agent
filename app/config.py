"""Configuration loaded from environment variables.

Sanitizes non-breaking spaces (copy-paste artifact from macOS)
per the pattern used in Image Creation Agent.
"""

import os


def _clean(value):
    """Strip Unicode non-breaking spaces and whitespace from env values."""
    if value is None:
        return None
    return value.replace("\xa0", "").strip()


# --- Database ---
DATABASE_URL = _clean(os.environ.get("DATABASE_URL"))

# --- Gmail OAuth2 ---
GMAIL_OAUTH_CREDENTIALS = _clean(os.environ.get("GMAIL_OAUTH_CREDENTIALS"))
GMAIL_OAUTH_TOKEN = _clean(os.environ.get("GMAIL_OAUTH_TOKEN"))
GMAIL_ADDRESS = _clean(os.environ.get("GMAIL_ADDRESS", "hello@sleepysaturday.com"))

# --- Ship24 ---
SHIP24_API_KEY = _clean(os.environ.get("SHIP24_API_KEY"))

# --- Flask ---
FLASK_SECRET_KEY = _clean(os.environ.get("FLASK_SECRET_KEY", "dev-secret-key"))

# --- Trigger auth ---
TRIGGER_SECRET_KEY = _clean(os.environ.get("TRIGGER_SECRET_KEY", "dev-trigger-key"))

# --- Scheduler ---
SCAN_INTERVAL_HOURS = int(os.environ.get("SCAN_INTERVAL_HOURS", "2"))
STATUS_CHECK_INTERVAL_HOURS = int(os.environ.get("STATUS_CHECK_INTERVAL_HOURS", "2"))

# --- Order matching: statuses eligible for tracking match ---
MATCHABLE_ORDER_STATUSES = {"SAMPLING", "IN_PRODUCTION", "SHIPPED"}
