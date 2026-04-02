"""Unit tests for app.scanner.tracking_patterns."""

import pytest

from app.scanner.tracking_patterns import (
    CARRIER_PATTERNS,
    find_tracking_numbers,
    find_tracking_urls,
)


# ── USPS ──────────────────────────────────────────────────────────────────

class TestUSPS:
    def test_20_digit_usps(self):
        """20-digit number starting with 94 is detected as USPS."""
        text = "Your tracking number is 94001234567890123456"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "USPS"]
        assert "94001234567890123456" in nums

    def test_22_digit_usps(self):
        """22-digit number starting with 92 is detected as USPS."""
        text = "Track: 9200190164917312345678"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "USPS"]
        assert "9200190164917312345678" in nums

    def test_international_format(self):
        """International format (2 letters + 9 digits + US) is detected."""
        text = "International parcel: EC123456789US"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "USPS"]
        assert "EC123456789US" in nums


# ── UPS ───────────────────────────────────────────────────────────────────

class TestUPS:
    def test_1z_tracking_number(self):
        """Standard 1Z format is detected as UPS."""
        text = "UPS tracking: 1Z999AA10123456784"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "UPS"]
        assert "1Z999AA10123456784" in nums

    def test_1z_lowercase_not_matched(self):
        """1z (lowercase) should NOT match — UPS uses uppercase 1Z."""
        text = "Not a real one: 1z999aa10123456784"
        results = find_tracking_numbers(text)
        ups = [r for r in results if r["carrier"] == "UPS"]
        assert len(ups) == 0


# ── FedEx ─────────────────────────────────────────────────────────────────

class TestFedEx:
    def test_12_digit_with_fedex_context(self):
        """12-digit number near 'FedEx' text -> carrier=FedEx."""
        text = "Your FedEx shipment 123456789012 is on the way."
        results = find_tracking_numbers(text)
        match = [r for r in results if r["number"] == "123456789012"]
        assert len(match) == 1
        assert match[0]["carrier"] == "FedEx"

    def test_15_digit_fedex(self):
        """15-digit number near 'FedEx' text -> carrier=FedEx."""
        text = "FedEx Ground tracking: 123456789012345"
        results = find_tracking_numbers(text)
        match = [r for r in results if r["number"] == "123456789012345"]
        assert len(match) == 1
        assert match[0]["carrier"] == "FedEx"


# ── DHL ───────────────────────────────────────────────────────────────────

class TestDHL:
    def test_10_digit_dhl(self):
        """10-digit number near 'DHL' text -> carrier=DHL."""
        text = "DHL Express shipment 1234567890 delivered."
        results = find_tracking_numbers(text)
        match = [r for r in results if r["number"] == "1234567890"]
        assert len(match) == 1
        assert match[0]["carrier"] == "DHL"

    def test_jd_prefix_dhl(self):
        """JD-prefixed alphanumeric is detected as DHL."""
        text = "Your DHL package JD012345678901234567 is in transit."
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "DHL"]
        assert "JD012345678901234567" in nums


# ── Amazon ────────────────────────────────────────────────────────────────

class TestAmazon:
    def test_tba_amazon(self):
        """TBA + 12 digits is detected as Amazon."""
        text = "Amazon delivery TBA123456789012"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "Amazon"]
        assert "TBA123456789012" in nums

    def test_tbm_amazon(self):
        """TBM prefix also detected as Amazon."""
        text = "Shipped via TBM987654321012345"
        results = find_tracking_numbers(text)
        nums = [r["number"] for r in results if r["carrier"] == "Amazon"]
        assert "TBM987654321012345" in nums


# ── Negative / edge cases ─────────────────────────────────────────────────

class TestNegativeCases:
    def test_random_words_not_detected(self):
        """Plain English text should produce no results."""
        text = "Hello, this is just a normal email about nothing."
        results = find_tracking_numbers(text)
        assert results == []

    def test_empty_string(self):
        """Empty input returns empty list."""
        assert find_tracking_numbers("") == []

    def test_short_numbers_ignored(self):
        """Numbers shorter than any carrier pattern are not matched."""
        text = "Order #12345 confirmed"
        results = find_tracking_numbers(text)
        assert results == []


# ── Multiple numbers in one string ────────────────────────────────────────

class TestMultipleNumbers:
    def test_multiple_carriers_in_one_text(self):
        """Two different carrier numbers in the same text both detected."""
        text = (
            "UPS tracking: 1Z999AA10123456784. "
            "Also USPS: 94001234567890123456."
        )
        results = find_tracking_numbers(text)
        numbers = {r["number"] for r in results}
        assert "1Z999AA10123456784" in numbers
        assert "94001234567890123456" in numbers


# ── Disambiguation ────────────────────────────────────────────────────────

class TestDisambiguation:
    def test_12_digit_near_fedex_text(self):
        """A 12-digit number (matches FedEx AND DHL) with 'FedEx' in
        surrounding text should resolve to FedEx."""
        text = "FedEx tracking number: 789012345678"
        results = find_tracking_numbers(text)
        match = [r for r in results if r["number"] == "789012345678"]
        assert len(match) == 1
        assert match[0]["carrier"] == "FedEx"

    def test_12_digit_without_context_defaults_to_fedex(self):
        """A 12-digit number only matches FedEx pattern, so FedEx wins (no ambiguity)."""
        text = "Tracking: 789012345678"
        results = find_tracking_numbers(text)
        match = [r for r in results if r["number"] == "789012345678"]
        assert len(match) == 1
        assert match[0]["carrier"] == "FedEx"


# ── Tracking URL extraction ───────────────────────────────────────────────

class TestTrackingURLs:
    def test_usps_url(self):
        text = "Track here: https://tools.usps.com/go/TrackConfirmAction?tLabels=94001234567890123456"
        results = find_tracking_urls(text)
        assert len(results) == 1
        assert results[0]["carrier"] == "USPS"
        assert results[0]["tracking_number"] == "94001234567890123456"

    def test_ups_url(self):
        text = "https://www.ups.com/track?tracknum=1Z999AA10123456784"
        results = find_tracking_urls(text)
        assert len(results) == 1
        assert results[0]["carrier"] == "UPS"
        assert results[0]["tracking_number"] == "1Z999AA10123456784"

    def test_fedex_url(self):
        text = "https://www.fedex.com/fedextrack/?trknbr=123456789012"
        results = find_tracking_urls(text)
        assert len(results) == 1
        assert results[0]["carrier"] == "FedEx"
        assert results[0]["tracking_number"] == "123456789012"

    def test_empty_string_returns_empty(self):
        assert find_tracking_urls("") == []


# ── CARRIER_PATTERNS exposed for testing ──────────────────────────────────

class TestCarrierPatternsExposed:
    def test_carrier_patterns_is_dict(self):
        assert isinstance(CARRIER_PATTERNS, dict)

    def test_all_five_carriers_present(self):
        expected = {"USPS", "UPS", "FedEx", "DHL", "Amazon"}
        assert set(CARRIER_PATTERNS.keys()) == expected
