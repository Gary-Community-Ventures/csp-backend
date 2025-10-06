from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, Type, TypeVar

T = TypeVar("T")


class Column(str, Generic[T]):
    def __new__(cls, name: str, converter: Callable[[Any], T] = str):
        instance = super().__new__(cls, name)
        instance._converter = converter
        return instance

    def __repr__(self):
        return f"Column({self}<{self._converter.__name__}>)"

    def __call__(self, data: dict) -> T:
        """
        Convert the value to the correct data type.
        """
        value = data[self]

        if value is None:
            return None
        return self._converter(value)


def datetime_column(value):
    return datetime.fromisoformat(value)


def date_column(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


E = TypeVar("E", bound=Enum)


def enum_column(enum_type: Type[E]) -> Callable[[Any], E]:
    def converter(value):
        return enum_type(value)

    return converter


class Status(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    DENIED = "Not Eligible"
    HOLD = "Hold"
    DUPLICATE = "Duplicate"
    WAIT_LIST = "Wait List"

    def _missing_(self, value) -> "Status":
        return Status.PENDING


class ProviderType(str, Enum):
    FFN = "ffn"
    CENTER = "center"
    LHB = "lhb"


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"

    @classmethod
    def _missing_(cls, value: object) -> "Language":
        return cls.ENGLISH
