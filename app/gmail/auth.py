"""Gmail OAuth2 token management for production.

Loads credentials and token from base64-encoded env vars so we never
store OAuth files on disk in production.  Automatically refreshes
expired access tokens using the stored refresh token.
"""

import base64
import json
import logging
import tempfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import GMAIL_OAUTH_CREDENTIALS, GMAIL_OAUTH_TOKEN

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _decode_env_var(value, name):
    """Base64-decode an env var and return parsed JSON dict."""
    if not value:
        raise RuntimeError(
            f"{name} env var is missing or empty. "
            "Run scripts/gmail_authorize.py first."
        )
    try:
        raw = base64.b64decode(value)
        return json.loads(raw)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode {name}. "
            "Make sure it contains valid base64-encoded JSON."
        ) from exc


def _build_credentials():
    """Build a google.oauth2.credentials.Credentials object from env vars."""
    creds_data = _decode_env_var(GMAIL_OAUTH_CREDENTIALS, "GMAIL_OAUTH_CREDENTIALS")
    token_data = _decode_env_var(GMAIL_OAUTH_TOKEN, "GMAIL_OAUTH_TOKEN")

    # Extract client_id and client_secret from the credentials file.
    # Google's credentials.json nests these under "installed" or "web".
    inner = creds_data.get("installed") or creds_data.get("web") or {}
    client_id = inner.get("client_id")
    client_secret = inner.get("client_secret")
    token_uri = inner.get("token_uri", "https://oauth2.googleapis.com/token")

    if not client_id or not client_secret:
        raise RuntimeError(
            "credentials.json is missing client_id or client_secret. "
            "Re-download it from Google Cloud Console."
        )

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    # Refresh if the access token has expired.
    if creds.expired and creds.refresh_token:
        logger.info("Gmail access token expired -- refreshing.")
        creds.refresh(Request())
        logger.info("Gmail access token refreshed successfully.")

    if not creds.valid:
        raise RuntimeError(
            "Gmail credentials are not valid and could not be refreshed. "
            "Re-run scripts/gmail_authorize.py to generate a new token."
        )

    return creds


def get_gmail_service():
    """Return an authenticated Gmail API service object.

    Call this whenever you need to interact with the Gmail API.
    It handles credential loading, decoding, and token refresh.
    """
    creds = _build_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    logger.info("Gmail API service created successfully.")
    return service
