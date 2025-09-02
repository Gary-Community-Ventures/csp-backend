from datetime import datetime
from typing import TYPE_CHECKING, Union

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

