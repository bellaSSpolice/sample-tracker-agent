"""One-time OAuth2 authorization script.

Run this locally (not on the server) to generate token.json.

Usage:
    1. Download your OAuth credentials from Google Cloud Console
       and save as credentials.json in THIS directory (scripts/).
    2. Run:  python scripts/gmail_authorize.py
    3. A browser window opens -- sign in and grant access.
    4. token.json is saved next to credentials.json.
    5. The script prints base64 strings for both files.
       Copy those into your Railway env vars:
         GMAIL_OAUTH_CREDENTIALS  <-- base64 of credentials.json
         GMAIL_OAUTH_TOKEN        <-- base64 of token.json
"""

import base64
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# These scopes let us read sent mail and create drafts (but NOT send).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")
TOKEN_PATH = os.path.join(SCRIPT_DIR, "token.json")


def main():
    # ------------------------------------------------------------------
    # 1. Make sure credentials.json exists
    # ------------------------------------------------------------------
    if not os.path.exists(CREDENTIALS_PATH):
        print(
            "ERROR: credentials.json not found.\n"
            "Download it from Google Cloud Console and place it in:\n"
            f"  {CREDENTIALS_PATH}"
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Run the OAuth consent flow (opens a browser)
    # ------------------------------------------------------------------
    print("Opening browser for Google OAuth consent...")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    # ------------------------------------------------------------------
    # 3. Save token.json
    # ------------------------------------------------------------------
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Token saved to {TOKEN_PATH}")

    # ------------------------------------------------------------------
    # 4. Print base64 versions for env var storage
    # ------------------------------------------------------------------
    with open(CREDENTIALS_PATH, "rb") as f:
        creds_b64 = base64.b64encode(f.read()).decode()

    with open(TOKEN_PATH, "rb") as f:
        token_b64 = base64.b64encode(f.read()).decode()

    print("\n" + "=" * 60)
    print("Copy these into your Railway environment variables:")
    print("=" * 60)
    print(f"\nGMAIL_OAUTH_CREDENTIALS=\n{creds_b64}\n")
    print(f"GMAIL_OAUTH_TOKEN=\n{token_b64}\n")
    print("=" * 60)
    print("Done! You can now deploy the app.")


if __name__ == "__main__":
    main()
