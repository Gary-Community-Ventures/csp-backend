from pydantic import BaseModel, Field


CENTS_PER_DOLLAR = 100
MIN_RATE = 1 * CENTS_PER_DOLLAR
MAX_RATE = 160 * CENTS_PER_DOLLAR


class PaymentRateBase(BaseModel):
    half_day_rate_cents: int = Field(..., ge=MIN_RATE, le=MAX_RATE)
    full_day_rate_cents: int = Field(..., ge=MIN_RATE, le=MAX_RATE)


class PaymentRateCreate(PaymentRateBase):
    pass


class PaymentRateResponse(PaymentRateBase):
    id: int

    model_config = {"from_attributes": True}
