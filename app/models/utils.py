from decimal import Decimal
from app.models.payment_rate import PaymentRate
from app.models.enums import CareDayType


def get_care_day_cost(day_type: CareDayType, provider_id: int, child_id: int) -> int:
    """Get the cost for a care day type from the payment rate"""
    rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)

    if not rate:
        raise ValueError(
            f"No payment rate found for provider {provider_id} and child {child_id}"
        )

    if day_type == CareDayType.FULL_DAY:
        return rate.full_day_rate_cents
    elif day_type == CareDayType.HALF_DAY:
        return rate.half_day_rate_cents
    else:
        raise ValueError(f"Invalid day type: {day_type}")