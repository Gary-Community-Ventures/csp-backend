from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.models.month_allocation import MonthAllocation, get_allocation_amount


@contextmanager
def frozen_business_clock(today: date):
    """Pin date_utils.datetime.now(...) to `today` so pre/post-cutoff behavior
    doesn't depend on when the test suite happens to run."""
    with patch("app.utils.date_utils.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(today.year, today.month, today.day)
        mock_dt.date.today.return_value = today
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        yield


def test_get_allocation_amount_prorated(db_session, app):
    """Test that the prorated allocation is returned when no month allocation exists"""
    # The mock_supabase fixture in app already has child data
    # Child 1 has monthly_allocation=1000.0, prorated_allocation=500.0
    amount = get_allocation_amount(child_id="1")
    assert amount == 50000  # prorated_allocation * 100


def test_get_allocation_amount_normal(month_allocation, app):
    """Test that the normal allocation is returned when a month allocation exists"""
    # When a month allocation exists, it should use monthly_allocation not prorated
    amount = get_allocation_amount(child_id="1")
    assert amount == 100000  # monthly_allocation * 100


def test_get_or_create_for_month_existing(db_session):
    """Test that the existing allocation is returned"""
    existing = MonthAllocation(child_supabase_id="1", date=date(2026, 3, 1), allocation_cents=100000)
    db_session.add(existing)
    db_session.commit()

    with frozen_business_clock(date(2026, 3, 15)):
        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 3, 1))
    assert allocation == existing


@patch("app.models.month_allocation.get_allocation_amount")
def test_get_or_create_for_month_new(mock_get_allocation_amount, db_session):
    """Test that a new allocation is created"""
    mock_get_allocation_amount.return_value = 50000

    with frozen_business_clock(date(2026, 3, 15)):
        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 3, 15))
    assert allocation.child_supabase_id == "1"
    assert allocation.date == date(2026, 3, 1)
    assert allocation.allocation_cents == 50000


def test_get_or_create_for_month_past(db_session):
    """Test that an error is raised when creating an allocation for a past month"""
    with pytest.raises(ValueError):
        MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2020, 1, 1))


def test_get_or_create_for_month_future(db_session):
    """Test that an error is raised when creating an allocation for a future month that is more than one month away"""
    with frozen_business_clock(date(2026, 3, 15)):
        with pytest.raises(ValueError, match="Cannot create allocation for a month more than one month in the future."):
            MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 6, 1))


@patch("app.models.month_allocation.get_allocation_amount")
def test_get_or_create_for_month_next_month_allowed(mock_get_allocation_amount, db_session):
    """Test that a new allocation for the next month can be created"""
    mock_get_allocation_amount.return_value = 50000

    with frozen_business_clock(date(2026, 3, 1)):
        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 4, 1))
    assert allocation.child_supabase_id == "1"
    assert allocation.date == date(2026, 4, 1)
    assert allocation.allocation_cents == 50000


@patch("app.models.month_allocation.get_allocation_amount")
def test_get_or_create_for_month_cutoff_rejected(mock_get_allocation_amount, db_session):
    """Allocations on/after the program-end cutoff are rejected."""
    # Simulate being in the month before the cutoff so the cutoff month passes
    # the "next month" check and the rejection comes specifically from the cutoff.
    with frozen_business_clock(date(2026, 6, 1)):
        with pytest.raises(ValueError, match="Cannot create allocation for .* or beyond."):
            MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 7, 1))

    # The cutoff fires before any allocation amount lookup.
    mock_get_allocation_amount.assert_not_called()


@patch("app.models.month_allocation.get_allocation_amount")
def test_get_or_create_for_month_last_month_before_cutoff_allowed(mock_get_allocation_amount, db_session):
    """The last month before the cutoff is still creatable."""
    mock_get_allocation_amount.return_value = 50000

    with frozen_business_clock(date(2026, 5, 1)):
        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2026, 6, 1))
    assert allocation.child_supabase_id == "1"
    assert allocation.date == date(2026, 6, 1)
    assert allocation.allocation_cents == 50000
