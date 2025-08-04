from pydantic import BaseModel, Field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

class AllocatedCareDayBase(BaseModel):
    date: date
    type: Literal["Full Day", "Half Day"]
    provider_google_sheets_id: int

class AllocatedCareDayCreate(AllocatedCareDayBase):
    care_month_allocation_id: int

class AllocatedCareDayResponse(AllocatedCareDayBase):
    id: int
    care_month_allocation_id: int
    amount_cents: int
    day_count: float
    payment_distribution_requested: bool
    last_submitted_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    locked_date: datetime
    is_locked: bool
    is_deleted: bool
    needs_resubmission: bool
    is_new_since_submission: bool
    delete_not_submitted: bool
    status: str

    class Config:
        from_attributes = True
