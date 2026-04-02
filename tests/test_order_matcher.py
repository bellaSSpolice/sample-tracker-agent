"""Tests for app.matcher.order_matcher."""

import uuid

import pytest

from app.matcher.order_matcher import match_order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order(mocker, tracking="TRACK123", client_id=None, status="IN_PRODUCTION"):
    order = mocker.MagicMock()
    order.id = uuid.uuid4()
    order.tracking_number = tracking
    order.client_id = client_id or uuid.uuid4()
    order.production_status = status
    return order


def _make_sample(mocker, tracking="SAMP456", order_id=None):
    sample = mocker.MagicMock()
    sample.id = uuid.uuid4()
    sample.tracking_number = tracking
    sample.order_id = order_id or uuid.uuid4()
    return sample


def _setup_session_for_order_matcher(mocker, order_first=None, sample_first=None,
                                      client_orders_all=None, parent_order_first=None):
    """Build a mock session that handles the sequential queries in match_order.

    match_order calls up to 4 queries in order:
        1. session.query(Order).filter(tracking == ...).first()   -> order_first
        2. session.query(Sample).filter(tracking == ...).first()  -> sample_first
        3. session.query(Order).filter(sample.order_id).first()   -> parent_order_first  (only if sample matched)
        4. session.query(Order).filter(client_id, status).all()   -> client_orders_all
    """
    session = mocker.MagicMock()

    # Each call to session.query() returns a new query mock. We use side_effect
    # to return different mocks for sequential calls.
    query_mocks = []

    # Query 1: Order by tracking_number -> .first()
    q1 = mocker.MagicMock()
    q1.filter.return_value.first.return_value = order_first
    query_mocks.append(q1)

    if order_first is None:
        # Query 2: Sample by tracking_number -> .first()
        q2 = mocker.MagicMock()
        q2.filter.return_value.first.return_value = sample_first
        query_mocks.append(q2)

        if sample_first is not None and sample_first.order_id:
            # Query 3: Parent Order for matched sample -> .first()
            q3 = mocker.MagicMock()
            q3.filter.return_value.first.return_value = parent_order_first
            query_mocks.append(q3)

        if sample_first is None:
            # Query 4: Client + status fallback -> .all()
            q4 = mocker.MagicMock()
            q4.filter.return_value.all.return_value = client_orders_all or []
            query_mocks.append(q4)

    session.query.side_effect = query_mocks
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMatchOrder:
    """Unit tests for match_order."""

    def test_direct_order_match(self, mocker):
        """A tracking number that exists directly on an Order returns that order
        with match_type='direct_order'."""
        order = _make_order(mocker, tracking="TRACK123")
        session = _setup_session_for_order_matcher(mocker, order_first=order)

        result = match_order("TRACK123", client_id=None, session=session)

        assert result["order"] is order
        assert result["sample"] is None
        assert result["match_type"] == "direct_order"

    def test_direct_sample_match(self, mocker):
        """A tracking number that exists on a Sample returns that sample and its
        parent order with match_type='direct_sample'."""
        parent = _make_order(mocker, tracking="ORD_PARENT")
        sample = _make_sample(mocker, tracking="SAMP456", order_id=parent.id)
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=sample,
            parent_order_first=parent,
        )

        result = match_order("SAMP456", client_id=None, session=session)

        assert result["sample"] is sample
        assert result["order"] is parent
        assert result["match_type"] == "direct_sample"

    def test_client_status_match_in_production(self, mocker):
        """If no direct tracking match, but the client has exactly one order in
        IN_PRODUCTION status, return it with match_type='client_status'."""
        client_id = uuid.uuid4()
        order = _make_order(mocker, tracking="OTHER", client_id=client_id, status="IN_PRODUCTION")
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=None,
            client_orders_all=[order],
        )

        result = match_order("UNKNOWN_TRACK", client_id=client_id, session=session)

        assert result["order"] is order
        assert result["sample"] is None
        assert result["match_type"] == "client_status"

    def test_client_status_match_sampling(self, mocker):
        """A single order in SAMPLING status for the client should match."""
        client_id = uuid.uuid4()
        order = _make_order(mocker, tracking="OTHER", client_id=client_id, status="SAMPLING")
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=None,
            client_orders_all=[order],
        )

        result = match_order("UNKNOWN_TRACK", client_id=client_id, session=session)

        assert result["order"] is order
        assert result["match_type"] == "client_status"

    def test_client_status_match_shipped(self, mocker):
        """A single order in SHIPPED status for the client should match."""
        client_id = uuid.uuid4()
        order = _make_order(mocker, tracking="OTHER", client_id=client_id, status="SHIPPED")
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=None,
            client_orders_all=[order],
        )

        result = match_order("UNKNOWN_TRACK", client_id=client_id, session=session)

        assert result["order"] is order
        assert result["match_type"] == "client_status"

    def test_client_multiple_eligible_orders_returns_none(self, mocker):
        """If the client has multiple eligible orders, do NOT auto-match --
        return None with match_type='none' and log a warning."""
        client_id = uuid.uuid4()
        order_a = _make_order(mocker, tracking="A", client_id=client_id, status="IN_PRODUCTION")
        order_b = _make_order(mocker, tracking="B", client_id=client_id, status="SHIPPED")
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=None,
            client_orders_all=[order_a, order_b],
        )

        mock_logger = mocker.patch("app.matcher.order_matcher.logger")

        result = match_order("UNKNOWN_TRACK", client_id=client_id, session=session)

        assert result["order"] is None
        assert result["sample"] is None
        assert result["match_type"] == "none"
        mock_logger.warning.assert_called_once()
        assert "Ambiguous" in mock_logger.warning.call_args[0][0]

    def test_no_match_at_all(self, mocker):
        """If nothing matches, return all-None with match_type='none'."""
        session = _setup_session_for_order_matcher(
            mocker,
            order_first=None,
            sample_first=None,
            client_orders_all=[],
        )

        result = match_order("NONEXISTENT", client_id=uuid.uuid4(), session=session)

        assert result["order"] is None
        assert result["sample"] is None
        assert result["match_type"] == "none"
