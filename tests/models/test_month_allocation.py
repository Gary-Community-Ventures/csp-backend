from datetime import date, datetime, timedelta
from unittest.mock import patch, Mock

import pytest

from app.models.month_allocation import MonthAllocation, get_allocation_amount




@patch('app.models.month_allocation.Child')
def test_get_allocation_amount_prorated(mock_child_class, db_session):
    """Test that the prorated allocation is returned when no month allocation exists"""
    # Mock the Supabase Child class
    mock_child_result = Mock()
    mock_child_class.select_by_id.return_value.execute.return_value = mock_child_result
    mock_child_class.MONTHLY_ALLOCATION.return_value = 1000.00
    mock_child_class.PRORATED_ALLOCATION.return_value = 500.00

    amount = get_allocation_amount(child_id="1")
    assert amount == 50000


@patch('app.models.month_allocation.Child')
def test_get_allocation_amount_normal(mock_child_class, month_allocation):
    """Test that the normal allocation is returned when a month allocation exists"""
    # Mock the Supabase Child class
    mock_child_result = Mock()
    mock_child_class.select_by_id.return_value.execute.return_value = mock_child_result
    mock_child_class.MONTHLY_ALLOCATION.return_value = 1000.00
    mock_child_class.PRORATED_ALLOCATION.return_value = 500.00

    amount = get_allocation_amount(child_id="1")
    assert amount == 100000


def test_get_or_create_for_month_existing(month_allocation):
    """Test that the existing allocation is returned"""
    today = date.today()
    allocation = MonthAllocation.get_or_create_for_month(
        child_id=month_allocation.child_supabase_id, month_date=today
    )
    assert allocation == month_allocation


@patch('app.models.month_allocation.get_allocation_amount')
def test_get_or_create_for_month_new(mock_get_allocation_amount, db_session):
    """Test that a new allocation is created"""
    # Mock the allocation amount function
    mock_get_allocation_amount.return_value = 50000
    
    today = date.today()
    allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=today)
    assert allocation.child_supabase_id == "1"
    assert allocation.date == today.replace(day=1)
    assert allocation.allocation_cents == 50000


def test_get_or_create_for_month_past(db_session):
    """Test that an error is raised when creating an allocation for a past month"""
    with pytest.raises(ValueError):
        MonthAllocation.get_or_create_for_month(child_id="1", month_date=date(2020, 1, 1))


def test_get_or_create_for_month_future(db_session):
    """Test that an error is raised when creating an allocation for a future month that is more than one month away"""
    with pytest.raises(ValueError, match="Cannot create allocation for a month more than one month in the future."):
        MonthAllocation.get_or_create_for_month(child_id="1", month_date=date.today() + timedelta(days=65))


@patch('app.models.month_allocation.get_allocation_amount')
def test_get_or_create_for_month_next_month_allowed(mock_get_allocation_amount, db_session):
    """Test that a new allocation for the next month can be created"""
    # Mock the allocation amount function
    mock_get_allocation_amount.return_value = 50000
    
    # Simulate being on the first day of the month
    with patch("app.utils.date_utils.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(date.today().year, date.today().month, 1)
        mock_dt.date.today.return_value = date(date.today().year, date.today().month, 1)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)  # Ensure other datetime calls work

        today = date.today()
        # Calculate the first day of the next month
        next_month_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)

        allocation = MonthAllocation.get_or_create_for_month(child_id="1", month_date=next_month_date)
        assert allocation.child_supabase_id == "1"
        assert allocation.date == next_month_date
        assert allocation.allocation_cents == 50000
