import zoneinfo
from datetime import date, datetime, timedelta
from typing import Tuple

from app.constants import BUSINESS_TIMEZONE, DAYS_TO_NEXT_MONTH


def get_current_month_start() -> date:
    business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
    now_business = datetime.now(business_tz)
    return now_business.date().replace(day=1)


def get_next_month_start() -> date:
    current_month = get_current_month_start()
    return (current_month + timedelta(days=DAYS_TO_NEXT_MONTH)).replace(day=1)


def get_week_range(target_date: date) -> Tuple[date, date]:
    # Monday is 0, Sunday is 6 in weekday()
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    return week_start, week_end
