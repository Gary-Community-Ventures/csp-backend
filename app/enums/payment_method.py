from enum import Enum


class PaymentMethod(str, Enum):
    VIRTUAL_CARD = "Virtual Card"
    ACH = "ACH"