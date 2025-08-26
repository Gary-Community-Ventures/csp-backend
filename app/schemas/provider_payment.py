from typing import Optional

from pydantic import BaseModel, Field


class PaymentMethodInitializeRequest(BaseModel):
    """Request schema for initializing provider payment method"""

    payment_method: str = Field(..., description="Payment method to initialize: 'card' or 'ach'")

    class Config:
        json_schema_extra = {"example": {"payment_method": "card"}}


class PaymentMethodUpdateRequest(BaseModel):
    """Request schema for updating provider payment method"""

    payment_method: str = Field(..., description="Payment method to switch to: 'card' or 'ach'")

    class Config:
        json_schema_extra = {"example": {"payment_method": "ach"}}


class PaymentSettingsResponse(BaseModel):
    """Response schema for provider payment settings"""

    provider_id: str = Field(..., description="External provider ID")
    chek_user_id: Optional[str] = Field(None, description="Chek user ID")
    payment_method: Optional[str] = Field(None, description="Current payment method: 'card' or 'ach'")
    payment_method_updated_at: Optional[str] = Field(None, description="ISO timestamp of last payment method update")
    payable: bool = Field(..., description="Whether provider is ready to receive payments")
    needs_refresh: bool = Field(..., description="Whether provider status needs refreshing from Chek")
    last_sync: Optional[str] = Field(None, description="ISO timestamp of last sync with Chek")
    card: dict = Field(..., description="Virtual card information and status")
    ach: dict = Field(..., description="ACH/DirectPay information and status")

    class Config:
        json_schema_extra = {
            "example": {
                "provider_id": "PROV123",
                "chek_user_id": "12345",
                "payment_method": "card",
                "payment_method_updated_at": "2024-01-15T10:30:00Z",
                "payable": True,
                "needs_refresh": False,
                "last_sync": "2024-01-15T10:30:00Z",
                "card": {"available": True, "status": "Active", "id": "card_67890"},
                "ach": {"available": True, "status": "Active", "id": "dp_54321"},
            }
        }


class PaymentMethodUpdateResponse(BaseModel):
    """Response schema for payment method updates"""

    message: str = Field(..., description="Success message")
    provider_id: str = Field(..., description="External provider ID")
    payment_method: str = Field(..., description="Updated payment method")
    payment_method_updated_at: str = Field(..., description="ISO timestamp of the update")
    payable: bool = Field(..., description="Whether provider is payable after update")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Payment method updated successfully",
                "provider_id": "PROV123",
                "payment_method": "ach",
                "payment_method_updated_at": "2024-01-15T10:30:00Z",
                "payable": True,
            }
        }
