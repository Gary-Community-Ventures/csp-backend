from datetime import datetime
from typing import Optional

from flask import current_app

from app.sheets.helpers import (
    Key,
    KeyMap,
    filter_rows_by_value,
    get_row,
    get_rows,
    money_to_float,
)


class FamilyColumnNames:
    SHEET_NAME = "Families"

    ID = Key("ID")
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    EMAIL = Key("Email")
    LANGUAGE = Key("Language", default="en")
    PHONE_NUMBER = Key("Phone Number")
    PAYMENT_ENABLED = Key("Payment Enabled", lambda v: v.lower() == "true", default=False)


class ChildColumnNames:
    SHEET_NAME = "Children"

    ID = Key("ID")
    FAMILY_ID = Key("Family ID")
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    BIRTH_DATE = Key("Birth Date")
    BALANCE = Key("Balance", money_to_float)
    MONTHLY_ALLOCATION = Key("Monthly Allocation", money_to_float)
    PRORATED_FIRST_MONTH_ALLOCATION = Key("Prorated First Month Allocation", money_to_float)
    STATUS = Key("Status")


class ProviderColumnNames:
    SHEET_NAME = "Providers"

    ID = Key("ID")
    NAME = Key("Name")
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    STATUS = Key("Status", default="Pending")
    EMAIL = Key("Email")
    LANGUAGE = Key("Language", default="en")
    PHONE_NUMBER = Key("Phone Number")
    TYPE = Key("Type")
    PAYMENT_ENABLED = Key("Payment Enabled", lambda v: v.lower() == "true", default=False)


class ContentColumnNames:
    SHEET_NAME = "Content"

    ID = Key("ID")
    CONTENT = Key("Content")


class ProviderChildMappingColumnNames:
    SHEET_NAME = "Provider Child Mappings"

    ID = Key("ID")
    PROVIDER_ID = Key("Provider ID")
    CHILD_ID = Key("Child ID")


class TransactionColumnNames:
    SHEET_NAME = "Transactions"

    ID = Key("ID")
    PROVIDER_CHILD_ID = Key("Provider Child ID")
    AMOUNT = Key("Amount", money_to_float)
    DATETIME = Key("Datetime", datetime.fromisoformat, datetime.now())


def get_families() -> list[KeyMap]:
    return current_app.sheets_manager.get_sheet_data(FamilyColumnNames.SHEET_NAME)


def get_family(family_id: str, families: list[KeyMap]) -> Optional[KeyMap]:
    return get_row(families, family_id)


def get_children() -> list[KeyMap]:
    return current_app.sheets_manager.get_sheet_data(ChildColumnNames.SHEET_NAME)


def get_child(child_id: str, children: list[KeyMap]) -> Optional[KeyMap]:
    return get_row(children, child_id)


def get_family_children(family_id: str, children: list[KeyMap]) -> list[KeyMap]:
    family_children = []
    for child in children:
        if child.get(ChildColumnNames.FAMILY_ID) == family_id:
            family_children.append(child)

    return family_children


def get_providers() -> list[KeyMap]:
    return current_app.sheets_manager.get_sheet_data(ProviderColumnNames.SHEET_NAME)


def get_provider(provider_id: str, providers: list[KeyMap]) -> Optional[KeyMap]:
    return get_row(providers, provider_id)


def get_provider_child_mappings() -> list[KeyMap]:
    return current_app.sheets_manager.get_sheet_data(ProviderChildMappingColumnNames.SHEET_NAME)


def get_provider_child_mappings_by_provider_id(provider_id: str, provider_child_mappings: list[KeyMap]) -> list[KeyMap]:
    return filter_rows_by_value(provider_child_mappings, provider_id, ProviderChildMappingColumnNames.PROVIDER_ID)


def get_provider_child_mappings_by_child_id(child_id: str, provider_child_mappings: list[KeyMap]) -> list[KeyMap]:
    return filter_rows_by_value(provider_child_mappings, child_id, ProviderChildMappingColumnNames.CHILD_ID)


def get_provider_child_mapping_child(
    provider_child_mapping_id: str, provider_child_mappings: list[KeyMap], children: list[KeyMap]
) -> Optional[KeyMap]:
    provider_child_mapping = get_row(provider_child_mappings, provider_child_mapping_id)

    return get_row(children, provider_child_mapping.get(ProviderChildMappingColumnNames.CHILD_ID))


def get_provider_child_mapping_provider(
    provider_child_mapping_id: str, provider_child_mappings: list[KeyMap], providers: list[KeyMap]
) -> Optional[KeyMap]:
    provider_child_mapping = get_row(provider_child_mappings, provider_child_mapping_id)

    return get_row(providers, provider_child_mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID))


def get_child_providers(child_id: str, provider_child_mappings: list[KeyMap], providers: list[KeyMap]) -> list[KeyMap]:
    provider_ids: list[str] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == child_id:
            provider_ids.append(mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID))

    return get_rows(providers, provider_ids)


def get_provider_children(
    provider_id: str, provider_child_mappings: list[KeyMap], children: list[KeyMap]
) -> list[KeyMap]:
    child_ids: list[str] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID) == provider_id:
            child_ids.append(mapping.get(ProviderChildMappingColumnNames.CHILD_ID))

    return get_rows(children, child_ids)


def get_transactions() -> list[KeyMap]:
    return current_app.sheets_manager.get_sheet_data(TransactionColumnNames.SHEET_NAME)


def get_transaction(transaction_id: str, transactions: list[KeyMap]) -> Optional[KeyMap]:
    return get_row(transactions, transaction_id)


def get_child_transactions(
    child_id: str, provider_child_mappings: list[KeyMap], transactions: list[KeyMap]
) -> list[KeyMap]:
    provider_child_ids: list[str] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == child_id:
            provider_child_ids.append(mapping.get(ProviderChildMappingColumnNames.ID))

    return get_rows(transactions, provider_child_ids, id_key=TransactionColumnNames.PROVIDER_CHILD_ID)


def get_provider_transactions(
    provider_id: str, provider_child_mappings: list[KeyMap], transactions: list[KeyMap]
) -> list[KeyMap]:
    provider_child_ids: list[str] = []
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID) == provider_id:
            provider_child_ids.append(mapping.get(ProviderChildMappingColumnNames.ID))

    return get_rows(transactions, provider_child_ids, id_key=TransactionColumnNames.PROVIDER_CHILD_ID)
