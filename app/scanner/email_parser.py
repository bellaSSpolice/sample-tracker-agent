from __future__ import annotations

"""Parse email subject/body to extract tracking numbers and URLs.

Uses tracking_patterns.py for the actual detection logic.
Handles HTML bodies via BeautifulSoup (strips tags, extracts href URLs).
"""

from bs4 import BeautifulSoup

from app.scanner.tracking_patterns import find_tracking_numbers, find_tracking_urls


def _extract_text_and_urls_from_html(html: str) -> tuple[str, str]:
    """Return (plain_text, urls_text) extracted from an HTML string.

    plain_text: visible text with tags stripped.
    urls_text:  all href attribute values separated by newlines (so tracking
                URLs inside <a> tags are still scannable).
    """
    soup = BeautifulSoup(html, "html.parser")
    plain_text = soup.get_text(separator=" ")

    href_urls: list[str] = []
    for tag in soup.find_all("a", href=True):
        href_urls.append(tag["href"])

    return plain_text, "\n".join(href_urls)


def parse_email_for_tracking(
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> list[dict]:
    """Scan an email's subject and body for tracking numbers and URLs.

    Parameters
    ----------
    subject : str
        The email subject line.
    body_text : str
        The plain-text version of the email body.
    body_html : str | None
        The HTML version of the email body (optional). If provided, it is
        parsed to extract visible text *and* href URLs.

    Returns
    -------
    list[dict]
        Each dict has the shape::

            {
                "tracking_number": "940...",
                "carrier": "USPS",
                "tracking_url": "https://..." or None,
            }

        Results are deduplicated by tracking_number (the same number found
        in both the subject and body only appears once).
    """
    # Build the combined text to scan.
    parts: list[str] = []
    if subject:
        parts.append(subject)
    if body_text:
        parts.append(body_text)

    extra_url_text = ""
    if body_html:
        html_plain, html_urls = _extract_text_and_urls_from_html(body_html)
        parts.append(html_plain)
        extra_url_text = html_urls

    combined_text = "\n".join(parts)

    # Run detection.
    numbers = find_tracking_numbers(combined_text)
    urls = find_tracking_urls(combined_text)

    # Also scan href URLs that were extracted from HTML <a> tags.
    if extra_url_text:
        urls.extend(find_tracking_urls(extra_url_text))

    # Build a lookup: tracking_number -> url info.
    url_by_number: dict[str, str] = {}
    for entry in urls:
        tn = entry.get("tracking_number")
        if tn and tn not in url_by_number:
            url_by_number[tn] = entry["url"]

    # Merge numbers + URL info, deduplicating by tracking_number.
    seen: set[str] = set()
    results: list[dict] = []

    # Start with numbers found via regex patterns.
    for item in numbers:
        tn = item["number"]
        if tn in seen:
            continue
        seen.add(tn)
        results.append(
            {
                "tracking_number": tn,
                "carrier": item["carrier"],
                "tracking_url": url_by_number.get(tn),
            }
        )

    # Add any URL-only tracking numbers not already captured.
    for entry in urls:
        tn = entry.get("tracking_number")
        if not tn or tn in seen:
            continue
        seen.add(tn)
        results.append(
            {
                "tracking_number": tn,
                "carrier": entry["carrier"],
                "tracking_url": entry["url"],
            }
        )

    return results
