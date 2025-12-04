from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


class AllocatedCareDayBase(BaseModel):
    date: date
    type: Literal["Full Day", "Half Day"]
    provider_supabase_id: str


class AllocatedCareDayCreate(AllocatedCareDayBase):
    care_month_allocation_id: int


class AllocatedCareDayResponse(AllocatedCareDayBase):
    id: int
    care_month_allocation_id: int
    amount_cents: int
    amount_missing_cents: Optional[int]
    day_count: float
    payment_distribution_requested: bool
    last_submitted_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    locked_date: datetime
    is_locked: bool
    is_deleted: bool
    is_partial_payment: bool
    needs_submission: bool
    status: str

    model_config = {"from_attributes": True}
