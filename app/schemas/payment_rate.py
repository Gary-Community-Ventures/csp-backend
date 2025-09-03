from pydantic import BaseModel, Field

from app.constants import MAX_PAYMENT_RATE, MIN_PAYMENT_RATE


class PaymentRateBase(BaseModel):
    half_day_rate_cents: int = Field(..., ge=MIN_PAYMENT_RATE, le=MAX_PAYMENT_RATE)
    full_day_rate_cents: int = Field(..., ge=MIN_PAYMENT_RATE, le=MAX_PAYMENT_RATE)


class PaymentRateCreate(PaymentRateBase):
    pass


class PaymentRateResponse(PaymentRateBase):
    id: int

    model_config = {"from_attributes": True}
