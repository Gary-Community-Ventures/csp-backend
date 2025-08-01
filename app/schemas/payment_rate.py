from pydantic import BaseModel, Field
from typing import Optional


class PaymentRateBase(BaseModel):
    google_sheets_provider_id: int
    google_sheets_child_id: int
    half_day_rate_cents: int = Field(..., gt=0, le=50000)
    full_day_rate_cents: int = Field(..., gt=0, le=50000)


class PaymentRateCreate(PaymentRateBase):
    pass


class PaymentRateUpdate(BaseModel):
    half_day_rate_cents: Optional[int] = Field(None, gt=0, le=50000)
    full_day_rate_cents: Optional[int] = Field(None, gt=0, le=50000)


class PaymentRateResponse(PaymentRateBase):
    id: int

    class Config:
        from_attributes = True