from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.care_day import AllocatedCareDayResponse


class MonthAllocationResponse(BaseModel):
    id: int
    date: date
    allocation_cents: int
    google_sheets_child_id: str
    remaining_unselected_cents: float
    remaining_unpaid_cents: float
    locked_until_date: date
    locked_past_date: date
    created_at: datetime
    updated_at: datetime
    care_days: list[AllocatedCareDayResponse]

    model_config = {"from_attributes": True}
