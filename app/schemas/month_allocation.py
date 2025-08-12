from pydantic import BaseModel
from datetime import date, datetime
from typing import List
from app.schemas.care_day import AllocatedCareDayResponse


class MonthAllocationResponse(BaseModel):
    id: int
    date: date
    allocation_cents: int
    google_sheets_child_id: str
    used_days: float
    used_cents: float
    remaining_cents: float
    over_allocation: bool
    locked_until_date: date
    created_at: datetime
    updated_at: datetime
    care_days: List[AllocatedCareDayResponse]

    model_config = {"from_attributes": True}
