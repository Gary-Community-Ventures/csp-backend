from pydantic import BaseModel
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List
from app.schemas.care_day import AllocatedCareDayResponse # Import the care day schema

class MonthAllocationResponse(BaseModel):
    id: int
    date: date
    allocation_cents: int
    google_sheets_child_id: int
    used_days: float
    used_cents: float
    remaining_cents: float
    over_allocation: bool
    locked_until_date: date # Add the new field
    created_at: datetime
    updated_at: datetime
    care_days: List[AllocatedCareDayResponse] # Add the care_days field

    model_config = {'from_attributes': True}
