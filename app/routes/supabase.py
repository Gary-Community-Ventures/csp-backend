from dataclasses import dataclass
from enum import Enum
from flask import Blueprint, jsonify, request, abort
from flask import current_app
from app.auth.decorators import api_key_required
from app.extensions import db
from app.models.payment_intent import PaymentIntent
from app.models.month_allocation import MonthAllocation
from app.models.allocated_lump_sum import AllocatedLumpSum
from app.models.provider_payment_settings import ProviderPaymentSettings
from app.models.family_payment_settings import FamilyPaymentSettings
from app.models.allocated_care_day import AllocatedCareDay
from app.models.attendance import Attendance
from app.models.family_invitation import FamilyInvitation
from app.models.payment_rate import PaymentRate
from app.models.provider_invitation import ProviderInvitation
from app.models.payment_request import PaymentRequest
from app.models.payment import Payment

bp = Blueprint("supabase", __name__)


@dataclass
class Mapping:
    old: str
    new: str


class MappingType(Enum):
    CHILD = "child"
    PROVIDER = "provider"
    FAMILY = "family"


class SupabaseMapping:
    class MigrationError(Exception):
        pass

    def __init__(
        self,
        table_name: str,
        Model,  # pylint: disable=invalid-name
        google_sheet_field: str,
        supabase_field: str,
        mapping_type: MappingType,
        has_multiple_records: bool = False,
    ):
        self.table_name = table_name
        self.Model = Model  # pylint: disable=invalid-name
        self.google_sheet_field = google_sheet_field
        self.supabase_field = supabase_field
        self.mapping_type = mapping_type
        self.has_multiple_records = has_multiple_records

    def migrate(self, mappings: list[Mapping], force: bool = False) -> list:
        google_sheet_field = getattr(self.Model, self.google_sheet_field)
        supabase_field = getattr(self.Model, self.supabase_field)

        updated = []
        for mapping in mappings:
            existing = self.Model.query.filter(supabase_field == mapping.new).count()
            if not force and existing > 0:
                raise self.MigrationError(
                    f"Record already exists for Supabase Id '{mapping.new}' {self._error_context()}"
                )

            records = self.Model.query.filter(google_sheet_field == mapping.old).all()

            if not force and len(records) == 0:
                continue
            elif not self.has_multiple_records and not force and len(records) > 1:
                raise self.MigrationError(
                    f"'{len(records)}' records found for Google Sheet Id '{mapping.old}' {self._error_context()}"
                )

            for record in records:
                setattr(record, self.supabase_field, mapping.new)
                updated.append(record)

        return updated

    def unmigrated_count(self) -> int:
        supabase_field = getattr(self.Model, self.supabase_field)

        return self.Model.query.filter(supabase_field.is_(None)).count()

    def update_count(self, dict) -> int:
        if self.table_name not in dict:
            dict[self.table_name] = {}

        count = self.unmigrated_count()
        dict[self.table_name][self.supabase_field] = count

        return count

    def _error_context(self):
        return f"[{self.table_name}:({self.google_sheet_field}->{self.supabase_field})]"


MIGRATION_MAPPINGS = [
    SupabaseMapping("payment_intents", PaymentIntent, "child_external_id", "child_supabase_id", MappingType.CHILD, has_multiple_records=True),
    SupabaseMapping(
        "payment_intents", PaymentIntent, "provider_external_id", "provider_supabase_id", MappingType.PROVIDER, has_multiple_records=True
    ),
    SupabaseMapping(
        "month_allocations", MonthAllocation, "google_sheets_child_id", "child_supabase_id", MappingType.CHILD
    ),
    SupabaseMapping(
        "provider_payment_settings",
        ProviderPaymentSettings,
        "provider_external_id",
        "provider_supabase_id",
        MappingType.PROVIDER,
    ),
    SupabaseMapping(
        "family_payment_settings", FamilyPaymentSettings, "family_external_id", "family_supabase_id", MappingType.FAMILY
    ),
    SupabaseMapping(
        "allocated_care_days",
        AllocatedCareDay,
        "provider_google_sheets_id",
        "provider_supabase_id",
        MappingType.PROVIDER,
        has_multiple_records=True,
    ),
    SupabaseMapping("attendance", Attendance, "child_google_sheet_id", "child_supabase_id", MappingType.CHILD, has_multiple_records=True),
    SupabaseMapping("attendance", Attendance, "provider_google_sheet_id", "provider_supabase_id", MappingType.PROVIDER, has_multiple_records=True),
    SupabaseMapping("payment_rates", PaymentRate, "google_sheets_child_id", "child_supabase_id", MappingType.CHILD, has_multiple_records=True),
    SupabaseMapping(
        "payment_rates", PaymentRate, "google_sheets_provider_id", "provider_supabase_id", MappingType.PROVIDER, has_multiple_records=True
    ),
    SupabaseMapping(
        "provider_invitations", ProviderInvitation, "child_google_sheet_id", "child_supabase_id", MappingType.CHILD
    ),
    SupabaseMapping(
        "payment_requests", PaymentRequest, "google_sheets_child_id", "child_supabase_id", MappingType.CHILD, has_multiple_records=True
    ),
    SupabaseMapping(
        "payment_requests", PaymentRequest, "google_sheets_provider_id", "provider_supabase_id", MappingType.PROVIDER, has_multiple_records=True
    ),
    SupabaseMapping(
        "allocated_lump_sums",
        AllocatedLumpSum,
        "provider_google_sheets_id",
        "provider_supabase_id",
        MappingType.PROVIDER,
        has_multiple_records=True,
    ),
    SupabaseMapping(
        "family_invitations", FamilyInvitation, "provider_google_sheet_id", "provider_supabase_id", MappingType.PROVIDER
    ),
    SupabaseMapping(
        "payment", Payment, "external_provider_id", "provider_supabase_id", MappingType.PROVIDER, has_multiple_records=True
    ),
    SupabaseMapping(
        "payment", Payment, "external_child_id", "child_supabase_id", MappingType.CHILD, has_multiple_records=True
    ),
]


@bp.post("/admin/migrate/supabase-ids")
@api_key_required
def migrate_supabase_ids():
    """
    Bulk migrate Google Sheet IDs to Supabase IDs across all tables.

    Request body:
    {
        "mappings": {
            "children": {"google_id": "supabase_id", ...},
            "providers": {"google_id": "supabase_id", ...},
            "families": {"google_id": "supabase_id", ...}
        },
        "dry_run": false
    }
    """
    data = request.json

    if not data or "mappings" not in data:
        abort(400, description="Missing required field: mappings")

    mappings = data["mappings"]
    dry_run = data.get("dry_run", True)

    child_mapping = mappings.get("children", {})
    provider_mapping = mappings.get("providers", {})
    family_mapping = mappings.get("families", {})

    results = {"dry_run": dry_run, "updated_counts": {}, "total_updated": 0}

    # Convert mappings to Mapping objects
    child_mappings = [Mapping(old=k, new=v) for k, v in child_mapping.items()]
    provider_mappings = [Mapping(old=k, new=v) for k, v in provider_mapping.items()]
    family_mappings = [Mapping(old=k, new=v) for k, v in family_mapping.items()]

    try:
        for migration in MIGRATION_MAPPINGS:
            if migration.mapping_type == MappingType.CHILD:
                mappings_to_use = child_mappings
            elif migration.mapping_type == MappingType.PROVIDER:
                mappings_to_use = provider_mappings
            elif migration.mapping_type == MappingType.FAMILY:
                mappings_to_use = family_mappings
            else:
                raise ValueError(f"Unknown mapping type: {migration.mapping_type}")

            updated_records = migration.migrate(mappings_to_use, force=data.get("force", False))
            count = len(updated_records)
            if not dry_run:
                db.session.add_all(updated_records)

            if migration.table_name not in results["updated_counts"]:
                results["updated_counts"][migration.table_name] = {}

            results["updated_counts"][migration.table_name][migration.supabase_field] = count
            results["total_updated"] += count

        if not dry_run:
            db.session.commit()

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Migration failed: {e}")
        abort(500, description=f"Migration failed: {str(e)}")

    return jsonify(results), 200


@bp.get("/admin/migrate/status")
@api_key_required
def migration_status():
    """
    Check the current status of ID migration.
    Returns count of records still needing migration.
    """
    total = 0
    unmigrated_counts = {}
    for migration in MIGRATION_MAPPINGS:
        total += migration.update_count(unmigrated_counts)

    status = {"unmigrated_counts": unmigrated_counts, "total_unmigrated": total}

    return jsonify(status), 200
