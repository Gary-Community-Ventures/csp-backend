from app.sheets.helpers import Key, KeyMap, get_row, get_rows, money_to_float
from app.sheets.integration import get_sheet_data
from datetime import datetime


class FamilyColumnNames:
    SHEET_NAME = "Families"

    ID = Key("ID", int)
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")


class ChildColumnNames:
    SHEET_NAME = "Children"

    ID = Key("ID", int)
    FAMILY_ID = Key("Family ID", int)
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    BIRTH_DATE = Key("Birth Date")
    BALANCE = Key("Balance", money_to_float)


class ProviderColumnNames:
    SHEET_NAME = "Providers"

    ID = Key("ID", int)
    NAME = Key("Name")
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    STATUS = Key("Status")


class ContentColumnNames:
    SHEET_NAME = "Content"

    ID = Key("ID", int)
    CONTENT = Key("Content")


class ProviderChildMappingColumnNames:
    SHEET_NAME = "Provider Child Mappings"

    ID = Key("ID", int)
    PROVIDER_ID = Key("Provider ID", int)
    CHILD_ID = Key("Child ID", int)


class TransactionColumnNames:
    SHEET_NAME = "Transactions"

    ID = Key("ID", int)
    PROVIDER_CHILD_ID = Key("Provider Child ID", int)
    AMOUNT = Key("Amount", money_to_float)
    DATETIME = Key("Datetime", datetime.fromisoformat)


def get_families() -> list[KeyMap]:
    return get_sheet_data(FamilyColumnNames.SHEET_NAME)


def get_family(family_id: int, families: list[KeyMap]) -> KeyMap:
    return get_row(families, family_id)


def get_children() -> list[KeyMap]:
    return get_sheet_data(ChildColumnNames.SHEET_NAME)


def get_child(child_id: int, children: list[KeyMap]) -> KeyMap:
    return get_row(children, child_id)


def get_family_children(family_id, children: list[KeyMap]) -> list[KeyMap]:
    family_children = []
    for child in children:
        if child.get(ChildColumnNames.FAMILY_ID) == family_id:
            family_children.append(child)

    return family_children


def get_providers() -> list[KeyMap]:
    return get_sheet_data(ProviderColumnNames.SHEET_NAME)


def get_provider(provider_id: int, providers: list[KeyMap]) -> KeyMap:
    return get_row(providers, provider_id)


def get_provider_child_mappings() -> list[KeyMap]:
    return get_sheet_data(ProviderChildMappingColumnNames.SHEET_NAME)


def get_provider_child_mapping_child(
    provider_child_mapping_id: int, provider_child_mappings: list[KeyMap], children: list[KeyMap]
) -> KeyMap:
    provider_child_mapping = get_row(provider_child_mappings, provider_child_mapping_id)

    return get_row(children, provider_child_mapping.get(ProviderChildMappingColumnNames.CHILD_ID))


def get_provider_child_mapping_provider(
    provider_child_mapping_id: int, provider_child_mappings: list[KeyMap], providers: list[KeyMap]
) -> KeyMap:
    provider_child_mapping = get_row(provider_child_mappings, provider_child_mapping_id)

    return get_row(providers, provider_child_mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID))


def get_child_providers(
    child_id: int, provider_child_mappings: list[KeyMap], providers: list[KeyMap]
) -> list[KeyMap]:
    provider_ids: list[int] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == child_id:
            provider_ids.append(mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID))

    return get_rows(providers, provider_ids)


def get_provider_children(
    provider_id: int, provider_child_mappings: list[KeyMap], children: list[KeyMap]
) -> list[KeyMap]:
    child_ids: list[int] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID) == provider_id:
            child_ids.append(mapping.get(ProviderChildMappingColumnNames.CHILD_ID))

    return get_rows(children, child_ids)


def get_transactions() -> list[KeyMap]:
    return get_sheet_data(TransactionColumnNames.SHEET_NAME)


def get_transaction(transaction_id: int, transactions: list[KeyMap]) -> KeyMap:
    return get_row(transactions, transaction_id)


def get_child_transactions(
    child_id: int, provider_child_mappings: list[KeyMap], transactions: list[KeyMap]
) -> list[KeyMap]:
    provider_child_ids: list[int] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == child_id:
            provider_child_ids.append(mapping.get(ProviderChildMappingColumnNames.ID))

    return get_rows(transactions, provider_child_ids, id_key=TransactionColumnNames.PROVIDER_CHILD_ID)

def get_provider_transactions(
    provider_id: int, provider_child_mappings: list[KeyMap], transactions: list[KeyMap]
) -> list[KeyMap]:
    provider_child_ids: list[int] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID) == provider_id:
            provider_child_ids.append(mapping.get(ProviderChildMappingColumnNames.ID))

    return get_rows(transactions, provider_child_ids, id_key=TransactionColumnNames.PROVIDER_CHILD_ID)
