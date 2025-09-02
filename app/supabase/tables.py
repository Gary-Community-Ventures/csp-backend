from flask import current_app
from postgrest import SyncRequestBuilder, SyncSelectRequestBuilder
from app.supabase.helpers import cols, date_column, datetime_column
from typing import Any, Callable, Generic, TypeVar

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


class Table:
    TABLE_NAME: str = ""
    ID: str = Column("id", int)

    @classmethod
    def query(cls) -> SyncRequestBuilder:
        return current_app.supabase_client.table(cls.TABLE_NAME)

    @classmethod
    def join(cls, *columns: str):
        return f"{cls.TABLE_NAME}({cols(*columns)})"

    @classmethod
    def select_by_id(cls, columns: str, id: str) -> SyncSelectRequestBuilder:
        return cls.query().select(columns).eq(cls.ID, id).single()

    @classmethod
    def unwrap(cls, data: dict):
        return data.get(cls.TABLE_NAME)


class Family(Table):
    TABLE_NAME = "family"

    CREATED_AT = Column("created_at", datetime_column)
    REFERRED_BY = Column("referred_by")
    SIZE = Column("size", int)
    YEARLY_INCOME = Column("yearly_income", float)
    ZIP = Column("zip")
    APPROVED = Column("approved", datetime_column)


class Guardian(Table):
    TABLE_NAME = "guardian"

    CREATED_AT = Column("created_at", datetime_column)
    TYPE = Column("type")
    FIRST_NAME = Column("first_name")
    LAST_NAME = Column("last_name")
    EMAIL = Column("email")
    PHONE_NUMBER = Column("phone_number")
    ADDRESS_1 = Column("address_1")
    ADDRESS_2 = Column("address_2")
    CITY = Column("city")
    STATE = Column("state")
    ZIP = Column("zip")

    # Foreign keys
    FAMILY_ID = Column("family", int)


class Child(Table):
    TABLE_NAME = "child"

    CREATED_AT = Column("created_at", datetime_column)
    FIRST_NAME = Column("first_name")
    MIDDLE_NAME = Column("middle_name")
    LAST_NAME = Column("last_name")
    DATE_OF_BIRTH = Column("dob", date_column)

    # Foreign keys
    FAMILY_ID = Column("family_id")


class Provider(Table):
    TABLE_NAME = "provider"

    CREATED_AT = Column("created_at", datetime_column)
    TYPE = Column("type")
    NAME = Column("name")
    ADDRESS_1 = Column("address_1")
    ADDRESS_2 = Column("address_2")
    CITY = Column("city")
    STATE = Column("state")
    ZIP = Column("zip")
    APPROVED = Column("approved", datetime_column)
