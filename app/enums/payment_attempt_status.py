from enum import Enum


class PaymentAttemptStatus(str, Enum):
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    WALLET_FUNDED = "wallet_funded"
