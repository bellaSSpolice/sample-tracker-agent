from __future__ import annotations

"""Regex patterns for detecting shipping carrier tracking numbers and URLs.

Supports USPS, UPS, FedEx, DHL, and Amazon tracking formats.
Uses word-boundary anchors to avoid matching numbers embedded in longer strings.
"""

import re
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Carrier tracking-number patterns
# ---------------------------------------------------------------------------
# Each value is a list of compiled regexes. A match on ANY regex in the list
# means the number belongs to that carrier (subject to disambiguation below).

CARRIER_PATTERNS: dict[str, list[re.Pattern]] = {
    "USPS": [
        # 20-digit numbers starting with 94, 93, 92, or 95
        re.compile(r"\b(9[2-5]\d{18})\b"),
        # 22-digit numbers starting with 94, 93, 92, or 95
        re.compile(r"\b(9[2-5]\d{20})\b"),
        # International format: 2 uppercase letters + 9 digits + "US"
        re.compile(r"\b([A-Z]{2}\d{9}US)\b"),
    ],
    "UPS": [
        # 1Z + 16 alphanumeric characters (total 18)
        re.compile(r"\b(1Z[0-9A-Z]{16})\b"),
    ],
    "FedEx": [
        # 12 digits
        re.compile(r"\b(\d{12})\b"),
        # 15 digits
        re.compile(r"\b(\d{15})\b"),
        # 20 digits (not starting with 9[2-5], which would be USPS)
        re.compile(r"\b((?!9[2-5])\d{20})\b"),
        # 22 digits (not starting with 9[2-5], which would be USPS)
        re.compile(r"\b((?!9[2-5])\d{22})\b"),
    ],
    "DHL": [
        # 10 digits
        re.compile(r"\b(\d{10})\b"),
        # Alphanumeric starting with JD, GM, LX, or RR followed by digits
        re.compile(r"\b((JD|GM|LX|RR)\d{10,20})\b"),
    ],
    "Amazon": [
        # Starts with TBA, TBM, or TBC followed by 12-15 digits
        re.compile(r"\b(TB[AMC]\d{12,15})\b"),
    ],
}

# Carrier names we look for in surrounding text when disambiguating.
_CARRIER_KEYWORDS: dict[str, list[str]] = {
    "USPS": ["usps", "united states postal", "postal service"],
    "UPS": ["ups", "united parcel"],
    "FedEx": ["fedex", "fed ex", "federal express"],
    "DHL": ["dhl"],
    "Amazon": ["amazon", "amzl"],
}

# ---------------------------------------------------------------------------
# Tracking-URL patterns
# ---------------------------------------------------------------------------
# Each entry: (compiled URL regex, carrier name, group index for tracking #)

_URL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"https?://tools\.usps\.com/go/TrackConfirmAction\?tLabels=([A-Za-z0-9]+)",
            re.IGNORECASE,
        ),
        "USPS",
    ),
    (
        re.compile(
            r"https?://(?:www\.)?ups\.com/track\?.*?tracknum=([A-Za-z0-9]+)",
            re.IGNORECASE,
        ),
        "UPS",
    ),
    (
        re.compile(
            r"https?://(?:www\.)?fedex\.com/fedextrack/?\?.*?trknbr=([A-Za-z0-9]+)",
            re.IGNORECASE,
        ),
        "FedEx",
    ),
    (
        re.compile(
            r"https?://(?:www\.)?dhl\.com/[^\s]*tracking\.html\?[^\s]*",
            re.IGNORECASE,
        ),
        "DHL",
    ),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _carrier_mentioned(carrier: str, text: str) -> bool:
    """Return True if the carrier name appears anywhere in *text*."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _CARRIER_KEYWORDS.get(carrier, []))


def find_tracking_numbers(text: str) -> list[dict]:
    """Detect tracking numbers in *text*.

    Returns a list of dicts:
        [{"number": "940...", "carrier": "USPS"}, ...]

    Disambiguation rules:
    - A number that matches only ONE carrier -> that carrier wins.
    - A number that matches multiple carriers -> check surrounding text for
      carrier keywords. If exactly one carrier is mentioned, use it.
    - Otherwise carrier = "unknown" (Ship24 will auto-detect).
    """
    if not text:
        return []

    # Collect every (number, carrier) pair.
    raw_matches: list[tuple[str, str]] = []
    for carrier, patterns in CARRIER_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                # Group 1 is the tracking number itself.
                number = match.group(1)
                raw_matches.append((number, carrier))

    # Group by number -> set of carriers that claimed it.
    number_to_carriers: dict[str, set[str]] = {}
    for number, carrier in raw_matches:
        number_to_carriers.setdefault(number, set()).add(carrier)

    # Disambiguate and build results.
    seen: set[str] = set()
    results: list[dict] = []
    for number, carriers in number_to_carriers.items():
        if number in seen:
            continue
        seen.add(number)

        if len(carriers) == 1:
            chosen = next(iter(carriers))
        else:
            # Check surrounding text for carrier keywords.
            mentioned = [c for c in carriers if _carrier_mentioned(c, text)]
            if len(mentioned) == 1:
                chosen = mentioned[0]
            else:
                chosen = "unknown"

        results.append({"number": number, "carrier": chosen})

    return results


def find_tracking_urls(text: str) -> list[dict]:
    """Extract tracking URLs from *text*.

    Returns a list of dicts:
        [{"url": "https://...", "carrier": "UPS", "tracking_number": "1Z..."}]

    For DHL, the tracking number is pulled from the query string param
    (typically ``submit`` or ``tracking-id``).
    """
    if not text:
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    for pattern, carrier in _URL_PATTERNS:
        for match in pattern.finditer(text):
            url = match.group(0)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if carrier == "DHL":
                # DHL URLs don't have a clean capture group — parse the QS.
                parsed = urlparse(url)
                qs = parse_qs(parsed.query)
                tracking_number = (
                    qs.get("submit", qs.get("tracking-id", [None]))[0]
                )
            else:
                tracking_number = match.group(1) if match.lastindex else None

            results.append(
                {
                    "url": url,
                    "carrier": carrier,
                    "tracking_number": tracking_number,
                }
            )

    return results
