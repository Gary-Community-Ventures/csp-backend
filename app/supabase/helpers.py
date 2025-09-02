from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from app.supabase.tables import Column


def cols(*args: "Column"):
    if len(args) == 0:
        return "*"

    return ", ".join([str(a) for a in args])


def by_id(query, id: str):
    return query.filter(id=id)


def datetime_column(value):
    return datetime.fromisoformat(value)


def date_column(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def enum_column(enum_type: Type[Enum]):
    def converter(value):
        return enum_type(value)

    return converter


class Status(str, Enum):
    PENDING = "Pending"
    DENIED = "Denied"
    APPROVED = "Approved"


class ProviderType(str, Enum):
    FFN = "ffn"
    CENTER = "center"
    LHB = "lhb"


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
