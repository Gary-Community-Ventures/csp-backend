from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, TypeVar, Type

T = TypeVar("T")


class Column(Generic[T]):
    def __init__(self, name: str, converter: Callable[[Any], T] = str):
        self.name = name
        self._converter = converter

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Column({self.name}<{self._converter.__name__}>)"

    def __call__(self, data: dict) -> T:
        """
        Convert the value to the correct data type.
        """
        value = data[self.name]

        if value is None:
            return None
        return self._converter(value)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, str):  # Allow it to be used as a key in a dict
            return self.name == other
        if isinstance(other, Column):
            return self.name == other.name

        return False


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
    DENIED = "Denied"
    APPROVED = "Approved"


class ProviderType(str, Enum):
    FFN = "ffn"
    CENTER = "center"
    LHB = "lhb"


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
