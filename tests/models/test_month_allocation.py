from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.month_allocation import MonthAllocation, get_allocation_amount
from app.sheets.helpers import KeyMap
from app.sheets.mappings import ChildColumnNames


@pytest.fixture
def mock_get_children():
    with patch("app.models.month_allocation.get_children") as mock:
        yield mock


def test_get_allocation_amount_prorated(mock_get_child, db_session, mock_get_children):
    """Test that the prorated allocation is returned when no month allocation exists"""
    mock_get_child.return_value = KeyMap(
        {
            ChildColumnNames.MONTHLY_ALLOCATION.key: "$1,000.00",
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "$500.00",
        }
    )

    amount = get_allocation_amount(child_id="1")
    assert amount == 50000


def test_get_allocation_amount_normal(mock_get_child, month_allocation, mock_get_children):
    """Test that the normal allocation is returned when a month allocation exists"""
    mock_get_child.return_value = KeyMap(
        {
            ChildColumnNames.MONTHLY_ALLOCATION.key: "$1,000.00",
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "$500.00",
        }
    )

    amount = get_allocation_amount(child_id="1")
    assert amount == 100000


def test_get_or_create_for_month_existing(month_allocation):
    """Test that the existing allocation is returned"""
    today = date.today()
    allocation = MonthAllocation.get_or_create_for_month(
        child_id=month_allocation.google_sheets_child_id, month_date=today
    )
    assert allocation == month_allocation


def test_get_or_create_for_month_new(db_session, mock_get_child, mock_get_children):
    """Test that a new allocation is created"""
    mock_get_child.return_value = KeyMap(
        {
            ChildColumnNames.MONTHLY_ALLOCATION.key: "$1,000.00",
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "$500.00",
        }
    )
    today = date.today()
    allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=today)
    assert allocation.google_sheets_child_id == "1"
    assert allocation.date == today.replace(day=1)
    assert allocation.allocation_cents == 50000


def test_get_or_create_for_month_past(db_session, mock_get_child, mock_get_children):
    """Test that an error is raised when creating an allocation for a past month"""
    with pytest.raises(ValueError):
        MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2020, 1, 1))


def test_get_or_create_for_month_future(db_session, mock_get_child, mock_get_children):
    """Test that an error is raised when creating an allocation for a future month that is more than one month away"""
    with pytest.raises(ValueError, match="Cannot create allocation for a month more than one month in the future."):
        MonthAllocation.get_or_create_for_month(child_id="1", month_date=date.today() + timedelta(days=65))


def test_get_or_create_for_month_next_month_allowed(db_session, mock_get_child, mock_get_children):
    """Test that a new allocation for the next month can be created"""
    mock_get_child.return_value = KeyMap(
        {
            ChildColumnNames.MONTHLY_ALLOCATION.key: "$1,000.00",
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "$500.00",
        }
    )
    # Simulate being on the first day of the month
    with patch("app.models.month_allocation.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(date.today().year, date.today().month, 1)
        mock_dt.date.today.return_value = date(date.today().year, date.today().month, 1)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)  # Ensure other datetime calls work

        today = date.today()
        # Calculate the first day of the next month
        next_month_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)

        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=next_month_date)
        assert allocation.google_sheets_child_id == "1"
        assert allocation.date == next_month_date
        assert allocation.allocation_cents == 50000
