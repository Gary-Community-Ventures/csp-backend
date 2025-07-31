from pydantic import BaseModel


class PaymentRateResponse(BaseModel):
    id: int
    google_sheets_provider_id: int
    google_sheets_child_id: int
    half_day_rate_cents: int
    full_day_rate_cents: int

    class Config:
        from_attributes = True