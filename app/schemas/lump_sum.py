from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AllocatedLumpSumResponse(BaseModel):
    id: int
    care_month_allocation_id: int
    provider_google_sheets_id: str
    amount_cents: int
    hours: Optional[float] = None
    paid_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AllocatedLumpSumCreateRequest(BaseModel):
    allocation_id: int
    provider_id: str
    amount_cents: int
    hours: float
