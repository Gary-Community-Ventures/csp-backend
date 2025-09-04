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
    id: Optional[str] = None
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
    balance: int  # In cents


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
    transfer: Optional[Dict[str, Any]] = Field(
        default=None, description="Transfer details including id, amount, created, type"
    )


class DirectPayAccount(BaseModel):
    id: Optional[str] = None
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
    counterparty_id: str
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


# --- Program Models ---


class ProgramParent(BaseModel):
    object_type: str
    display_string: str


class Program(BaseModel):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    name: str
    balance: int  # Balance in cents
    parent: ProgramParent


class ProgramListResponse(BaseModel):
    next: Optional[str] = None
    previous: Optional[str] = None
    count: int
    page_size: int
    page_count: int
    results: List[Program]


# --- Transfer Funds to Card Models ---


class TransferFundsToCardDirection(str, Enum):
    ALLOCATE_TO_CARD = "allocate_to_card"
    REMIT_FROM_CARD = "remit_from_card"


class TransferFundsToCardFundingMethod(str, Enum):
    WALLET = "wallet"
    PROGRAM = "program"


class TransferFundsToCardRequest(BaseModel):
    direction: TransferFundsToCardDirection
    funding_method: TransferFundsToCardFundingMethod
    amount: int


class TransferFundsToCardUser(BaseModel):
    """Simplified user info from card transfer response"""

    id: int
    email: str
    first_name: str
    last_name: str
    balance: int


class TransferFundsToCardInfo(BaseModel):
    """Card info from transfer response with balance"""

    id: str
    last4: str
    balance: int
    status: str
    type: str
    created: datetime


class TransferFundsToCardTransfer(BaseModel):
    """Transfer details from card funding response"""

    id: int
    amount: int
    created: datetime
    type: str  # e.g., "Wallet to Card"


class TransferFundsToCardResponse(BaseModel):
    """Response from transferring funds to a card"""

    user: TransferFundsToCardUser
    card: TransferFundsToCardInfo
    transfer: TransferFundsToCardTransfer


# --- ACH Payment Models ---


class ACHPaymentType(str, Enum):
    SAME_DAY_ACH = "same_day_ach"


class ACHFundingSource(str, Enum):
    WALLET = "wallet"


class ACHPaymentRequest(BaseModel):
    amount: int
    type: ACHPaymentType
    funding_source: ACHFundingSource
    program_id: int


class ACHPaymentUser(BaseModel):
    """Simplified user info from ACH payment response"""

    id: int
    email: str


class ACHPaymentProgram(BaseModel):
    """Simplified program info from ACH payment response"""

    id: int
    name: str


class ACHPaymentResponse(BaseModel):
    """Response from Chek API for ACH payment requests"""

    payment_id: str
    status: str
    amount: int = Field(..., description="Amount in cents")
    descriptor: str
    created: datetime = Field(..., description="Payment creation timestamp")
    receiving_bank_account: str
    funding_source: str
    user: ACHPaymentUser
    program: ACHPaymentProgram
