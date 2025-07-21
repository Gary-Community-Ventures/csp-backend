from typing import Callable, TypeVar, Generic

T = TypeVar("T")


class Key(Generic[T]):
    def __init__(self, key: str, converter: Callable[[str], T] = str):
        self.key = key
        self._converter = converter

    def convert(self, value: str) -> T:
        return self._converter(value)


class KeyMap(dict):
    def get(self, key: Key[T]) -> T:
        return key.convert(self[key.key])


ID_COLUMN_KEY = Key("ID", int)


def get_row_by_id(data: list[KeyMap], id: int) -> KeyMap:
    for item in data:
        if item.get(ID_COLUMN_KEY) == id:
            return item

    return None


def get_rows_by_ids(data: list[KeyMap], ids: list[int]) -> list[KeyMap]:
    items = []
    for item in data:
        if item.get(ID_COLUMN_KEY) in ids:
            items.append(item)

    return items


def money_to_float(money: str) -> float:
    return float(money.replace("$", "").replace(",", ""))
