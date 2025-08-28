from typing import Callable, Generic, Optional, TypeVar

from flask import current_app

T = TypeVar("T")


_NOT_ENTERED = object()


class Key(Generic[T]):
    def __init__(self, key: str, converter: Callable[[str], T] = str, default=_NOT_ENTERED):
        self.key = key
        self._converter = converter

        if default is _NOT_ENTERED and self._converter is str:
            self.default: T = "[MISSING]"
        elif default is _NOT_ENTERED:
            self.default: T = self._converter()
        else:
            self.default = default

    def convert(self, value: str) -> T:
        try:
            return self._converter(value)
        except ValueError:
            current_app.logger.error(f"Failed to convert value '{value}' to type '{self._converter}'")
            return self.default

    def __str__(self):
        return self.key

    def __repr__(self):
        return f"Key({self.key})"


class KeyMap(dict):
    def get(self, key: Key[T]) -> T:
        if key.key not in self or self[key.key] is None:
            return key.default

        return key.convert(self[key.key])


ID_COLUMN_KEY = Key("ID")


def get_row(data: list[KeyMap], id: str, id_key: Key[str] = ID_COLUMN_KEY) -> Optional[KeyMap]:
    for item in data:
        if item.get(id_key) == id:
            return item

    return None


def get_rows(data: list[KeyMap], ids: list[str], id_key: Key[str] = ID_COLUMN_KEY) -> list[KeyMap]:
    items = []
    for item in data:
        if item.get(id_key) in ids:
            items.append(item)

    return items


def filter_rows_by_value(data: list[KeyMap], value: T, key: Key[T]) -> list[KeyMap]:
    items = []
    for item in data:
        if item.get(key) == value:
            items.append(item)

    return items


def money_to_float(money: str = "0") -> float:
    return float(money.replace("$", "").replace(",", ""))


def boolean_from_str(value: str) -> bool:
    return value.strip().lower() == "true"


FIRST_NAME_KEY = Key("First Name", str)
LAST_NAME_KEY = Key("Last Name", str)


def format_name(
    data: KeyMap, first_name_key: Key[str] = FIRST_NAME_KEY, last_name_key: Key[str] = LAST_NAME_KEY
) -> str:
    return f"{data.get(first_name_key)} {data.get(last_name_key)}"
