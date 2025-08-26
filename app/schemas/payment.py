from typing import List, Optional

from pydantic import BaseModel, Field

from .care_day import AllocatedCareDayResponse


class PaymentProcessedResponse(BaseModel):
    """Response for successful care day payment processing"""

    message: str = "Payment processed successfully"
    total_amount: str = Field(..., description="Total payment amount in dollars (e.g., '$25.00')")
    care_days: List[AllocatedCareDayResponse] = Field(..., description="List of care days that were paid")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Payment processed successfully",
                "total_amount": "$125.00",
                "care_days": [
                    {
                        "id": 123,
                        "care_month_allocation_id": 456,
                        "date": "2024-01-15",
                        "type": "Full Day",
                        "amount_cents": 5000,
                        "day_count": 1.0,
                        "provider_google_sheets_id": "PROV123",
                    }
                ],
            }
        }


class PaymentErrorResponse(BaseModel):
    """Standard error response for payment operations"""

    error: str = Field(..., description="Error message describing what went wrong")

    class Config:
        json_schema_extra = {"example": {"error": "Payment processing failed. Provider not payable."}}


class PaymentStatusResponse(BaseModel):
    """Response for payment status queries"""

    payment_id: str
    status: str = Field(..., description="Payment status: 'pending', 'success', 'failed'")
    amount_cents: int
    provider_id: str
    child_id: str
    created_at: str
    last_attempt_error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "payment_id": "uuid-string",
                "status": "success",
                "amount_cents": 5000,
                "provider_id": "PROV123",
                "child_id": "CHILD456",
                "created_at": "2024-01-15T10:30:00Z",
                "last_attempt_error": None,
            }
        }


class PaymentInitializationResponse(BaseModel):
    """Response for payment method initialization"""

    message: str
    payment_method: str = Field(..., description="Initialized payment method: 'card' or 'ach'")
    provider_id: str
    chek_user_id: Optional[str] = None
    card_id: Optional[str] = Field(None, description="Card ID if payment method is 'card'")
    direct_pay_id: Optional[str] = Field(None, description="DirectPay ID if payment method is 'ach'")
    invite_sent_to: Optional[str] = Field(None, description="Email address for ACH invite")
    already_exists: bool = Field(default=False, description="Whether payment method already existed")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Virtual card created successfully",
                "payment_method": "card",
                "provider_id": "PROV123",
                "chek_user_id": "12345",
                "card_id": "card_67890",
                "direct_pay_id": None,
                "invite_sent_to": None,
                "already_exists": False,
            }
        }
