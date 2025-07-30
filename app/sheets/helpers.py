from typing import Callable, Optional, TypeVar, Generic

T = TypeVar("T")


class Key(Generic[T]):
    def __init__(self, key: str, converter: Callable[[str], T] = str):
        self.key = key
        self._converter = converter

    def convert(self, value: str) -> T:
        return self._converter(value)

    def __str__(self):
        return self.key

    def __repr__(self):
        return f"Key({self.key})"


class KeyMap(dict):
    def get(self, key: Key[T]) -> T:
        return key.convert(self[key.key])


ID_COLUMN_KEY = Key("ID", int)


def get_row(data: list[KeyMap], id: int, id_key: Key[int] = ID_COLUMN_KEY) -> Optional[KeyMap]:
    for item in data:
        if item.get(id_key) == id:
            return item

    return None


def get_rows(data: list[KeyMap], ids: list[int], id_key: Key[int] = ID_COLUMN_KEY) -> list[KeyMap]:
    items = []
    for item in data:
        if item.get(id_key) in ids:
            items.append(item)

    return items


def money_to_float(money: str) -> float:
    return float(money.replace("$", "").replace(",", ""))
