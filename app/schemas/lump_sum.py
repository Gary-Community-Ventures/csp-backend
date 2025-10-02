from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AllocatedLumpSumResponse(BaseModel):
    id: int
    care_month_allocation_id: int
    provider_supabase_id: str
    amount_cents: int
    paid_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    days: Optional[int] = None
    half_days: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AllocatedLumpSumCreateRequest(BaseModel):
    allocation_id: int
    provider_id: str
    amount_cents: int
    days: Optional[int] = None
    half_days: Optional[int] = None
