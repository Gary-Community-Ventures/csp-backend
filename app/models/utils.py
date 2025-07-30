from decimal import Decimal

def get_care_day_cost(day_type: str) -> Decimal:
    """Get the cost for a care day type - hardcoded for now"""
    costs = {"Full Day": Decimal("60.00"), "Half Day": Decimal("40.00")}
    return costs.get(day_type, Decimal("0.00"))