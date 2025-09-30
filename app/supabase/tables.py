from flask import current_app
from postgrest import SyncRequestBuilder, SyncSelectRequestBuilder

from app.supabase.columns import (
    Column,
    Language,
    ProviderType,
    Status,
    date_column,
    datetime_column,
    enum_column,
)
from app.supabase.helpers import cols


class Table:
    TABLE_NAME = ""
    ID = Column("id")

    @classmethod
    def query(cls) -> SyncRequestBuilder:
        return current_app.supabase_client.table(cls.TABLE_NAME)

    @classmethod
    def join(cls, *columns: str):
        return f"{cls.TABLE_NAME}({cols(*columns)})"

    @classmethod
    def select_by_id(cls, columns: str, id: int) -> SyncSelectRequestBuilder:
        return cls.query().select(columns).eq(cls.ID, id).single()

    @classmethod
    def unwrap(cls, data: dict):
        return data[cls.TABLE_NAME]

    @classmethod
    def find_by_id(cls, data: list[dict], id: str):
        for row in data:
            if cls.ID(row) == id:
                return row

        return None


class Family(Table):
    TABLE_NAME = "family"

    CREATED_AT = Column("created_at", datetime_column)
    REFERRED_BY = Column("referred_by")
    SIZE = Column("size", int)
    YEARLY_INCOME = Column("yearly_income", float)
    ZIP = Column("zip")
    LANGUAGE = Column("language", enum_column(Language))


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

    @classmethod
    def get_primary_guardian(cls, data: list[dict]) -> dict:
        for g in data:
            if cls.TYPE(g).lower() == "primary":
                return g

        return None


class Child(Table):
    TABLE_NAME = "child"

    CREATED_AT = Column("created_at", datetime_column)
    FIRST_NAME = Column("first_name")
    MIDDLE_NAME = Column("middle_name")
    LAST_NAME = Column("last_name")
    DATE_OF_BIRTH = Column("dob", date_column)
    MONTHLY_ALLOCATION = Column("monthly_allocation", float)
    PRORATED_ALLOCATION = Column("prorated_allocation", float)
    STATUS = Column("status", enum_column(Status))
    PAYMENT_ENABLED = Column("payment_enabled", bool)

    # Foreign keys
    FAMILY_ID = Column("family_id")

    @classmethod
    def select_by_family_id(cls, columns: str, family_id: int) -> SyncSelectRequestBuilder:
        return cls.query().select(columns).eq(cls.FAMILY_ID, family_id)


class Provider(Table):
    TABLE_NAME = "provider"

    CREATED_AT = Column("created_at", datetime_column)
    NAME = Column("name")
    FIRST_NAME = Column("first_name")
    LAST_NAME = Column("last_name")
    EMAIL = Column("email")
    PHONE_NUMBER = Column("phone")
    STATUS = Column("status", enum_column(Status))
    TYPE = Column("type", enum_column(ProviderType))
    PAYMENT_ENABLED = Column("payment_enabled", bool)
    ADDRESS_1 = Column("care_location_address_1")
    ADDRESS_2 = Column("care_location_address_2")
    CITY = Column("care_location_city")
    STATE = Column("care_location_state")
    ZIP = Column("care_location_zip")
    LANGUAGE = Column("language", enum_column(Language))
    CPR_CERTIFIED = Column("cpr_certified")
    CPR_TRAINING_LINK = Column("cpr_training_link")
    CPR_ONLINE_TRAINING_COMPLETED_AT = Column("cpr_online_training_completed_at", datetime_column)
    CHILD_SAFETY_MODULE_TRAINING_COMPLETED_AT = Column("child_safety_module_training_completed_at", datetime_column)
    SAFE_SLEEP_FOR_INFANTS_TRAINING_COMPLETED_AT = Column(
        "safe_sleep_for_infants_training_completed_at", datetime_column
    )
    HOME_SAFETY_AND_INJURY_PREVENTION_TRAINING_COMPLETED_AT = Column(
        "home_safety_and_injury_prevention_training_completed_at", datetime_column
    )
    PDIS_FIRST_AID_CPR_COMPLETED_AT = Column("pdis_first_aid_cpr_completed_at", datetime_column)
    PDIS_STANDARD_PRECAUTIONS_COMPLETED_AT = Column("pdis_standard_precautions_completed_at", datetime_column)
    PDIS_PREVENTING_CHILD_ABUSE_COMPLETED_AT = Column("pdis_preventing_child_abuse_completed_at", datetime_column)
    PDIS_INFANT_SAFE_SLEEP_COMPLETED_AT = Column("pdis_infant_safe_sleep_completed_at", datetime_column)
    PDIS_EMERGENCY_PREPAREDNESS_COMPLETED_AT = Column("pdis_emergency_preparedness_completed_at", datetime_column)
    PDIS_INJURY_PREVENTION_COMPLETED_AT = Column("pdis_injury_prevention_completed_at", datetime_column)
    PDIS_PREVENTING_SHAKEN_BABY_COMPLETED_AT = Column("pdis_preventing_shaken_baby_completed_at", datetime_column)
    PDIS_RECOGNIZING_IMPACT_OF_BIAS_COMPLETED_AT = Column(
        "pdis_recognizing_impact_of_bias_completed_at", datetime_column
    )
    PDIS_MEDICATION_ADMINISTRATION_PART_ONE_COMPLETED_AT = Column(
        "pdis_medication_administration_part_one_completed_at", datetime_column
    )


class ProviderChildMapping(Table):
    TABLE_NAME = "provider_child_mapping"

    CREATED_AT = Column("created_at", datetime_column)
    PROVIDER_ID = Column("provider_id")
    CHILD_ID = Column("child_id")
