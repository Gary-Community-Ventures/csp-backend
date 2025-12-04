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
