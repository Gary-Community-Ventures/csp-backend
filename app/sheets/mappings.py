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


class CaregiverColumnNames:
    SHEET_NAME = "Caregivers"

    ID = Key("ID", int)
    NAME = Key("Name")
    FIRST_NAME = Key("First Name")
    LAST_NAME = Key("Last Name")
    STATUS = Key("Status")


class ContentColumnNames:
    SHEET_NAME = "Content"

    ID = Key("ID", int)
    CONTENT = Key("Content")


class CaregiverChildMappingColumnNames:
    SHEET_NAME = "Caregiver Child Mappings"

    ID = Key("ID", int)
    CAREGIVER_ID = Key("Caregiver ID", int)
    CHILD_ID = Key("Child ID", int)


class TransactionColumnNames:
    SHEET_NAME = "Transactions"

    ID = Key("ID", int)
    CAREGIVER_CHILD_ID = Key("Caregiver Child ID", int)
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


def get_caregivers() -> list[KeyMap]:
    return get_sheet_data(CaregiverColumnNames.SHEET_NAME)


def get_caregiver(caregiver_id: int, caregivers: list[KeyMap]) -> KeyMap:
    return get_row(caregivers, caregiver_id)


def get_caregiver_child_mappings() -> list[KeyMap]:
    return get_sheet_data(CaregiverChildMappingColumnNames.SHEET_NAME)


def get_caregiver_child_mapping_child(
    caregiver_child_mapping_id: int, caregiver_child_mappings: list[KeyMap], children: list[KeyMap]
) -> KeyMap:
    caregiver_child_mapping = get_row(caregiver_child_mappings, caregiver_child_mapping_id)

    return get_row(children, caregiver_child_mapping.get(CaregiverChildMappingColumnNames.CHILD_ID))


def get_caregiver_child_mapping_caregiver(
    caregiver_child_mapping_id: int, caregiver_child_mappings: list[KeyMap], caregivers: list[KeyMap]
) -> KeyMap:
    caregiver_child_mapping = get_row(caregiver_child_mappings, caregiver_child_mapping_id)

    return get_row(caregivers, caregiver_child_mapping.get(CaregiverChildMappingColumnNames.CAREGIVER_ID))


def get_child_caregivers(
    child_id: int, caregiver_child_mappings: list[KeyMap], caregivers: list[KeyMap]
) -> list[KeyMap]:
    caregiver_ids: list[int] = []
    for mapping in caregiver_child_mappings:
        if mapping.get(CaregiverChildMappingColumnNames.CHILD_ID) == child_id:
            caregiver_ids.append(mapping.get(CaregiverChildMappingColumnNames.CAREGIVER_ID))

    return get_rows(caregivers, caregiver_ids)


def get_caregiver_children(
    caregiver_id: int, caregiver_child_mappings: list[KeyMap], children: list[KeyMap]
) -> list[KeyMap]:
    child_ids: list[int] = []
    for mapping in caregiver_child_mappings:
        if mapping.get(CaregiverChildMappingColumnNames.CAREGIVER_ID) == caregiver_id:
            child_ids.append(mapping.get(CaregiverChildMappingColumnNames.CHILD_ID))

    return get_rows(children, child_ids)


def get_transactions() -> list[KeyMap]:
    return get_sheet_data(TransactionColumnNames.SHEET_NAME)


def get_transaction(transaction_id: int, transactions: list[KeyMap]) -> KeyMap:
    return get_row(transactions, transaction_id)


def get_child_transactions(
    child_id: int, caregiver_child_mappings: list[KeyMap], transactions: list[KeyMap]
) -> list[KeyMap]:
    caregiver_child_ids: list[int] = []
    for mapping in caregiver_child_mappings:
        if mapping.get(CaregiverChildMappingColumnNames.CHILD_ID) == child_id:
            caregiver_child_ids.append(mapping.get(CaregiverChildMappingColumnNames.ID))

    return get_rows(transactions, caregiver_child_ids, id_key=TransactionColumnNames.CAREGIVER_CHILD_ID)
