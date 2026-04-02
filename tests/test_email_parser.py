"""Unit tests for app.scanner.email_parser."""

import pytest

from app.scanner.email_parser import parse_email_for_tracking


class TestRealisticUSPSEmail:
    def test_usps_tracking_in_plain_text_body(self):
        """Realistic USPS shipping confirmation email."""
        subject = "Your order has shipped!"
        body = (
            "Hi there,\n\n"
            "Great news -- your order #10452 has shipped via USPS.\n"
            "Tracking number: 94001234567890123456\n\n"
            "You can expect delivery in 3-5 business days.\n"
            "Thanks for shopping with us!"
        )
        results = parse_email_for_tracking(subject=subject, body_text=body)
        tracking_nums = [r["tracking_number"] for r in results]
        assert "94001234567890123456" in tracking_nums
        match = [r for r in results if r["tracking_number"] == "94001234567890123456"]
        assert match[0]["carrier"] == "USPS"


class TestHTMLOnlyEmail:
    def test_html_body_with_empty_text(self):
        """When body_text is empty but body_html has a tracking number."""
        html = (
            "<html><body>"
            "<p>Your FedEx package is on its way!</p>"
            "<p>Tracking: <b>123456789012345</b></p>"
            "</body></html>"
        )
        results = parse_email_for_tracking(
            subject="Shipment Notification",
            body_text="",
            body_html=html,
        )
        tracking_nums = [r["tracking_number"] for r in results]
        assert "123456789012345" in tracking_nums


class TestTrackingURLInHref:
    def test_href_url_extracted(self):
        """A tracking URL hidden inside an <a href> is extracted."""
        html = (
            '<html><body>'
            '<p>Track your package:</p>'
            '<a href="https://tools.usps.com/go/TrackConfirmAction?tLabels=94009876543210987654">'
            'Click here</a>'
            '</body></html>'
        )
        results = parse_email_for_tracking(
            subject="Your order shipped",
            body_text="",
            body_html=html,
        )
        # The tracking number should be found (via URL or regex).
        tracking_nums = [r["tracking_number"] for r in results]
        assert "94009876543210987654" in tracking_nums
        # The tracking URL should be populated.
        match = [r for r in results if r["tracking_number"] == "94009876543210987654"]
        assert match[0]["tracking_url"] is not None
        assert "usps.com" in match[0]["tracking_url"]


class TestNoTrackingNumber:
    def test_normal_email_returns_empty(self):
        """A regular email with no tracking info returns an empty list."""
        results = parse_email_for_tracking(
            subject="Meeting tomorrow at 10am",
            body_text="Hi team, let's meet at 10am in the conference room.",
        )
        assert results == []


class TestDeduplication:
    def test_same_number_in_subject_and_body(self):
        """The same tracking number in subject AND body appears only once."""
        number = "1Z999AA10123456784"
        subject = f"UPS Shipment {number}"
        body = f"Your package {number} has been picked up by UPS."
        results = parse_email_for_tracking(subject=subject, body_text=body)
        matches = [r for r in results if r["tracking_number"] == number]
        assert len(matches) == 1
        assert matches[0]["carrier"] == "UPS"


class TestMultipleDifferentNumbers:
    def test_two_different_carriers(self):
        """Email mentioning two different tracking numbers returns both."""
        subject = "Your orders have shipped"
        body = (
            "Order #1 shipped via UPS: 1Z999AA10123456784\n"
            "Order #2 shipped via USPS: 94001234567890123456\n"
        )
        results = parse_email_for_tracking(subject=subject, body_text=body)
        tracking_nums = {r["tracking_number"] for r in results}
        assert "1Z999AA10123456784" in tracking_nums
        assert "94001234567890123456" in tracking_nums
        assert len(tracking_nums) >= 2
