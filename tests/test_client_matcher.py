"""Tests for app.matcher.client_matcher."""

import uuid

import pytest

from app.matcher.client_matcher import match_client, _extract_domain


# ---------------------------------------------------------------------------
# Helper: build a mock Client object
# ---------------------------------------------------------------------------

def _make_client(mocker, email="info@windsorcourthotel.com", name="Windsor Court Hotel"):
    client = mocker.MagicMock()
    client.id = uuid.uuid4()
    client.name = name
    client.contact_email = email
    client.delivery_notification_enabled = True
    return client


# ---------------------------------------------------------------------------
# Helper: configure the mock session to return results for a LIKE filter
# ---------------------------------------------------------------------------

def _setup_session(mocker, results):
    """Return a mock session whose .query(Client).filter(...).all() returns *results*."""
    session = mocker.MagicMock()
    query = mocker.MagicMock()
    filtered = mocker.MagicMock()

    session.query.return_value = query
    query.filter.return_value = filtered
    filtered.all.return_value = results

    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractDomain:
    """Unit tests for the internal _extract_domain helper."""

    def test_normal_email(self):
        assert _extract_domain("john@windsorcourthotel.com") == "windsorcourthotel.com"

    def test_subdomain_email(self):
        assert _extract_domain("user@mail.company.com") == "mail.company.com"

    def test_uppercase(self):
        assert _extract_domain("USER@Example.COM") == "example.com"

    def test_empty_string(self):
        assert _extract_domain("") is None

    def test_no_at_sign(self):
        assert _extract_domain("not-an-email") is None

    def test_multiple_at_signs(self):
        assert _extract_domain("bad@@email.com") is None


class TestMatchClient:
    """Unit tests for match_client."""

    def test_exact_domain_match_returns_client(self, mocker):
        """A recipient email whose domain matches a client's contact_email domain
        should return that client."""
        client = _make_client(mocker, email="info@windsorcourthotel.com")
        session = _setup_session(mocker, results=[client])

        result = match_client("john@windsorcourthotel.com", session)

        assert result is client

    def test_no_match_returns_none(self, mocker):
        """If no client has a matching domain, return None."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@unknown-domain.com", session)

        assert result is None

    def test_multiple_matches_returns_first_and_logs_warning(self, mocker):
        """If multiple clients share the same domain, return the first and log
        a warning about the ambiguity."""
        client_a = _make_client(mocker, email="sales@bigcorp.com", name="BigCorp Sales")
        client_b = _make_client(mocker, email="support@bigcorp.com", name="BigCorp Support")
        session = _setup_session(mocker, results=[client_a, client_b])

        mock_logger = mocker.patch("app.matcher.client_matcher.logger")

        result = match_client("user@bigcorp.com", session)

        assert result is client_a
        mock_logger.warning.assert_called_once()
        assert "Multiple clients" in mock_logger.warning.call_args[0][0]

    def test_gmail_address_returns_none(self, mocker):
        """Personal email domains like gmail.com should be skipped entirely."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@gmail.com", session)

        assert result is None
        # The session should NOT have been queried at all.
        session.query.assert_not_called()

    def test_yahoo_address_returns_none(self, mocker):
        """yahoo.com is a personal domain and should be skipped."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@yahoo.com", session)

        assert result is None
        session.query.assert_not_called()

    def test_hotmail_address_returns_none(self, mocker):
        """hotmail.com is a personal domain and should be skipped."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@hotmail.com", session)

        assert result is None
        session.query.assert_not_called()

    def test_outlook_address_returns_none(self, mocker):
        """outlook.com is a personal domain and should be skipped."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@outlook.com", session)

        assert result is None
        session.query.assert_not_called()

    def test_aol_address_returns_none(self, mocker):
        """aol.com is a personal domain and should be skipped."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@aol.com", session)

        assert result is None
        session.query.assert_not_called()

    def test_icloud_address_returns_none(self, mocker):
        """icloud.com is a personal domain and should be skipped."""
        session = _setup_session(mocker, results=[])

        result = match_client("someone@icloud.com", session)

        assert result is None
        session.query.assert_not_called()

    def test_subdomain_email_extracts_full_domain(self, mocker):
        """An email like user@mail.company.com should extract 'mail.company.com'
        as the domain and query for it."""
        session = _setup_session(mocker, results=[])

        result = match_client("user@mail.company.com", session)

        # No match expected (empty results), but the query should have been called.
        assert result is None
        session.query.assert_called_once()
