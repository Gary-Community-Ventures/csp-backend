import zoneinfo
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.constants import BUSINESS_TIMEZONE, DAYS_TO_NEXT_MONTH


def get_month_start(date: date) -> date:
    return date.replace(day=1)


def get_current_month_start() -> date:
    business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
    now_business = datetime.now(business_tz)
    return get_month_start(now_business.date())


def get_next_month_start() -> date:
    current_month = get_current_month_start()
    return get_month_start(current_month + timedelta(days=DAYS_TO_NEXT_MONTH))


def get_relative_month(months_till: int = 0, from_date: Optional[date] = None) -> date:
    """Get the first day of a month relative to a reference date.

    Args:
        months_till: Number of months to offset (negative for past, positive for future)
        from_date: Reference date to calculate from (defaults to current business date)

    Returns:
        First day of the target month

    Examples:
        get_relative_month(0)   # Current month start
        get_relative_month(-1)  # Previous month start
        get_relative_month(1)   # Next month start
    """
    if from_date is None:
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        from_date = datetime.now(business_tz).date()

    # Get first day of the reference month
    month_start = from_date.replace(day=1)

    # Navigate to the target month
    # Convert to 0-indexed for easier arithmetic
    total_months = (month_start.year * 12 + month_start.month - 1) + months_till

    year = total_months // 12
    month = (total_months % 12) + 1

    return date(year, month, 1)


def get_week_range(target_date: date) -> tuple[date, date]:
    # Monday is 0, Sunday is 6 in weekday()
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    return week_start, week_end


def get_relative_week(weeks_till: int = 0, from_date: Optional[date] = None) -> date:
    if from_date is None:
        from_date = datetime.now(timezone.utc).date()

    monday = from_date - timedelta(days=from_date.weekday())

    return monday + timedelta(days=7 * weeks_till)
