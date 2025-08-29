"""
Result classes for PaymentService operations to provide consistent return types.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    payment_id: Optional[str] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # Type of error for handling
    provider_id: Optional[str] = None
    amount_cents: Optional[int] = None

    def __bool__(self) -> bool:
        """Allow using the result in boolean contexts."""
        return self.success

    @classmethod
    def success_result(cls, payment_id: str, provider_id: str, amount_cents: int):
        """Create a successful payment result."""
        return cls(success=True, payment_id=payment_id, provider_id=provider_id, amount_cents=amount_cents)

    @classmethod
    def failure_result(cls, error_message: str, error_type: str, provider_id: Optional[str] = None):
        """Create a failed payment result."""
        return cls(success=False, error_message=error_message, error_type=error_type, provider_id=provider_id)
