from supabase.client import Client, create_client

s: Client = create_client("todo", "todo")


def columns(*args: str):
    if len(args) == 0:
        return "*"

    return ", ".join(args)


class Table:
    TABLE_NAME: str = ""
    ID: str = "id"

    @classmethod
    def query(cls):
        return s.table(cls.TABLE_NAME)

    @classmethod
    def join(cls, *columns: str):
        return [f"{cls.TABLE_NAME}({c})" for c in columns]


class Family(Table):
    TABLE_NAME = "family"

    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"


class Child(Table):
    TABLE_NAME = "child"

    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FAMILY_ID = "family_id"


data = Child.query().select(columns(Child.FIRST_NAME, Child.LAST_NAME, *Family.join(Family.FIRST_NAME, Family.LAST_NAME))).exec
