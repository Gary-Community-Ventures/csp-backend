from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Address(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country_code: str


class DirectPayInfo(BaseModel):
    id: int
    bank_name: Optional[str] = None
    last4: Optional[str] = None
    status: str
    created: datetime


class CardInfo(BaseModel):
    id: str
    last4: str
    status: str
    type: str
    created: datetime


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    added: datetime
    last_login: Optional[datetime] = None
    directpay: Optional[DirectPayInfo] = None
    b2b_pay: Any = None  # Or a more specific model if needed
    cards: List[CardInfo]


class UserCreateResponse(BaseModel):
    id: int
    created: datetime
    first_name: str
    last_name: str
    email: str
    phone: str
    billing_address: Address
    balance: int


class CardArt(BaseModel):
    id: int
    display_string: str
    front_image: str
    back_image: str
    text_color: str


class Card(BaseModel):
    id: int
    created_at: datetime
    card_type: str
    status: str
    tag: Optional[str] = None
    preset: Any = None  # Or a more specific model if needed
    last4: str
    program: str
    card_art: CardArt
    metafields: List[Any]


class CardCreateResponse(BaseModel):
    """Response from the new card creation endpoint"""

    user: Dict[str, Any] = Field(description="User details including balance")
    program: Dict[str, Any] = Field(description="Program details including balance")
    card: Dict[str, Any] = Field(description="Card details including id, last4, status, type, created")
    transfer: Dict[str, Any] = Field(description="Transfer details including id, amount, created, type")


class DirectPayAccount(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    user: Dict[str, Any]  # Simplified for now
    status: str
    bank_name: Optional[str] = None
    last4: Optional[str] = None
    type: str
    billing_address: Optional[Address] = None
    custom_fields: Any = None
    balance_owed: Any = None
    outbound_payments: List[Any]


# --- Request Models ---


class UserCreateRequest(BaseModel):
    email: str
    phone: str = Field(pattern=r"^\+[1-9]\d{1,14}$")  # E.164 format
    first_name: str
    last_name: str
    address: Address


class CardCreateRequest(BaseModel):
    """Request for creating a card using the new endpoint"""

    program_id: int
    funding_method: str = Field(default="wallet_balance", description="Either 'wallet_balance' or 'program_balance'")
    amount: int = Field(description="Amount in cents to fund the card")


class DirectPayAccountInviteRequest(BaseModel):
    user_id: int


# --- Transfer Balance Models ---


class FlowDirection(str, Enum):
    PROGRAM_TO_WALLET = "program_to_wallet"
    WALLET_TO_PROGRAM = "wallet_to_program"
    WALLET_TO_WALLET = "wallet_to_wallet"


class TransferBalanceRequest(BaseModel):
    flow_direction: FlowDirection
    program_id: str
    amount: int  # In cents
    description: Optional[str] = None  # Optional description for the transfer
    metadata: Optional[dict] = None  # Optional metadata for tracking


class SourceDestination(BaseModel):
    id: int
    balance: int
    type: str


class TransferDetails(BaseModel):
    id: int
    amount: int
    created: datetime


class TransferBalanceResponse(BaseModel):
    source: SourceDestination
    destination: SourceDestination
    transfer: TransferDetails


# --- ACH Payment Models ---


class ACHPaymentType(str, Enum):
    SAME_DAY_ACH = "same_day_ach"


class ACHFundingSource(str, Enum):
    WALLET_BALANCE = "wallet_balance"


class ACHPaymentRequest(BaseModel):
    amount: int
    type: ACHPaymentType
    funding_source: ACHFundingSource
