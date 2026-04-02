"""Manually trigger one email scan (for local testing).

Usage:
    python scripts/run_scan_once.py

Requires DATABASE_URL, GMAIL_OAUTH_CREDENTIALS, GMAIL_OAUTH_TOKEN,
and SHIP24_API_KEY env vars to be set (or in .env file).
"""

import os
import sys

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()

with app.app_context():
    from app.scanner.scan_job import run_email_scan
    run_email_scan()
    print("Scan complete. Check logs above for details.")
