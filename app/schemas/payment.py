from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field

from .care_day import AllocatedCareDayResponse


class PaymentCareDayDetail(BaseModel):
    """Care day details for payment history"""

    date: date_type = Field(..., description="Date of the care day")
    type: str = Field(..., description="Type of care day: 'Full Day' or 'Half Day'")
    amount_cents: int = Field(..., description="Amount paid for this care day in cents")
    amount_missing_cents: Optional[int] = Field(None, description="Amount not covered by allocation (partial payment)")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-15",
                "type": "Full Day",
                "amount_cents": 5000,
                "amount_missing_cents": None,
            }
        }


class PaymentProcessedResponse(BaseModel):
    """Response for successful care day payment processing"""

    message: str = "Payment processed successfully"
    total_amount: str = Field(..., description="Total payment amount in dollars (e.g., '$25.00')")
    care_days: list[AllocatedCareDayResponse] = Field(..., description="List of care days that were paid")

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
                        "provider_supabase_id": "PROV123",
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


class FamilyPaymentHistoryItem(BaseModel):
    """Individual payment item in family payment history"""

    payment_id: str = Field(..., description="Unique payment ID")
    created_at: str = Field(..., description="ISO timestamp of when payment was created")
    amount_cents: int = Field(..., description="Payment amount in cents")
    status: str = Field(..., description="Payment status: 'success', 'failed', 'pending'")
    provider_name: str = Field(..., description="Name of the provider who received payment")
    provider_supabase_id: str = Field(..., description="Provider external ID")
    child_name: str = Field(..., description="Name of the child")
    child_supabase_id: str = Field(..., description="Child external ID")
    month: str = Field(..., description="Month the payment was for (YYYY-MM)")
    payment_type: str = Field(..., description="Type of payment: 'care_days' or 'lump_sum'")
    care_days: list[PaymentCareDayDetail] = Field(
        default_factory=list, description="Care days included in this payment"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "payment_id": "123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2024-01-15T10:30:00Z",
                "amount_cents": 5000,
                "status": "success",
                "provider_name": "ABC Daycare",
                "provider_id": "PROV123",
                "child_name": "John Doe",
                "child_id": "CHILD456",
                "month": "2024-01",
                "payment_type": "care_days",
            }
        }


class FamilyPaymentHistoryResponse(BaseModel):
    """Response for family payment history endpoint"""

    payments: list[FamilyPaymentHistoryItem] = Field(..., description="List of payments ordered by newest first")
    total_count: int = Field(..., description="Total number of payments")
    total_amount_cents: int = Field(..., description="Total amount of all payments in cents")

    class Config:
        json_schema_extra = {"example": {"payments": [], "total_count": 5, "total_amount_cents": 25000}}


class ProviderPaymentHistoryItem(BaseModel):
    """Individual payment item in provider payment history"""

    payment_id: str = Field(..., description="Unique payment ID")
    created_at: str = Field(..., description="ISO timestamp of when payment was created")
    amount_cents: int = Field(..., description="Payment amount in cents")
    status: str = Field(..., description="Payment status: 'success', 'failed', 'pending'")
    child_name: str = Field(..., description="Name of the child")
    child_id: str = Field(..., description="Child external ID")
    month: str = Field(..., description="Month the payment was for (YYYY-MM)")
    payment_method: str = Field(..., description="Payment method used: 'card' or 'ach'")
    payment_type: str = Field(..., description="Type of payment: 'care_days' or 'lump_sum'")
    care_days: list[PaymentCareDayDetail] = Field(
        default_factory=list, description="Care days included in this payment"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "payment_id": "123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2024-01-15T10:30:00Z",
                "amount_cents": 5000,
                "status": "success",
                "child_name": "John Doe",
                "child_id": "CHILD456",
                "month": "2024-01",
                "payment_method": "card",
                "payment_type": "care_days",
            }
        }


class ProviderPaymentHistoryResponse(BaseModel):
    """Response for provider payment history endpoint"""

    payments: list[ProviderPaymentHistoryItem] = Field(..., description="List of payments ordered by newest first")
    total_count: int = Field(..., description="Total number of payments")
    total_amount_cents: int = Field(..., description="Total amount of all payments in cents")
    successful_payments_cents: int = Field(..., description="Total amount of successful payments in cents")

    class Config:
        json_schema_extra = {
            "example": {
                "payments": [],
                "total_count": 10,
                "total_amount_cents": 50000,
                "successful_payments_cents": 45000,
            }
        }
