import zoneinfo
from datetime import date, datetime, timedelta

from app.constants import BUSINESS_TIMEZONE, DAYS_TO_NEXT_MONTH


def get_current_month_start() -> date:
    business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
    now_business = datetime.now(business_tz)
    return now_business.date().replace(day=1)


def get_next_month_start() -> date:
    current_month = get_current_month_start()
    return (current_month + timedelta(days=DAYS_TO_NEXT_MONTH)).replace(day=1)
