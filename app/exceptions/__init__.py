"""
Custom exceptions for the CSP Backend application.
These provide consistent error handling across the application.
"""


class CSPBackendException(Exception):
    """Base exception for all CSP Backend exceptions."""

    pass


class PaymentException(CSPBackendException):
    """Base exception for payment-related errors."""

    pass


class ProviderNotFoundException(PaymentException):
    """Raised when a provider cannot be found."""

    pass


class ProviderNotPayableException(PaymentException):
    """Raised when a provider is not eligible for payment."""

    pass


class PaymentLimitExceededException(PaymentException):
    """Raised when a payment exceeds configured limits."""

    pass


class AllocationExceededException(PaymentException):
    """Raised when a payment would exceed the monthly allocation."""

    pass


class InvalidPaymentStateException(PaymentException):
    """Raised when payment items are in an invalid state (e.g., not submitted)."""

    pass


class PaymentMethodException(PaymentException):
    """Base exception for payment method issues."""

    pass


class PaymentMethodNotConfiguredException(PaymentMethodException):
    """Raised when a provider has no payment method configured."""

    pass


class PaymentMethodNotAvailableException(PaymentMethodException):
    """Raised when a requested payment method is not available."""

    pass


class ChekServiceException(PaymentException):
    """Raised when Chek service operations fail."""

    pass


class ChekTransferException(ChekServiceException):
    """Raised when a Chek transfer fails."""

    pass


class ChekACHException(ChekServiceException):
    """Raised when a Chek ACH payment fails."""

    pass


class ValidationException(CSPBackendException):
    """Raised for validation errors."""

    pass


class DataNotFoundException(CSPBackendException):
    """Raised when required data is not found."""

    pass
