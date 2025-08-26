from enum import Enum


class PaymentMethod(str, Enum):
    CARD = "card"
    ACH = "ach"