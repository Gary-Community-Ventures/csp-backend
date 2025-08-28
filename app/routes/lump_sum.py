from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.auth.helpers import get_family_user
from app.extensions import db
from app.models.allocated_lump_sum import AllocatedLumpSum
from app.models.month_allocation import MonthAllocation
from app.schemas.lump_sum import AllocatedLumpSumCreateRequest, AllocatedLumpSumResponse
from app.sheets.mappings import (
    ChildColumnNames,
    FamilyColumnNames,
    ProviderColumnNames,
    get_child_providers,
    get_children,
    get_families,
    get_family,
    get_family_children,
    get_provider_child_mappings,
    get_providers,
)
from app.utils.email_service import send_lump_sum_payment_request_email

bp = Blueprint("lump_sum", __name__, url_prefix="/lump-sums")


@bp.post("")
@auth_required(ClerkUserType.FAMILY)
def create_lump_sum():
    user = get_family_user()

    family_id = user.user_data.family_id

    try:
        request_data = AllocatedLumpSumCreateRequest.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    allocation_id = request_data.allocation_id
    provider_id = request_data.provider_id
    amount_cents = request_data.amount_cents
    hours = request_data.hours

    allocation = db.session.get(MonthAllocation, allocation_id)
    if not allocation:
        return jsonify({"error": "MonthAllocation not found"}), 404

    # Check if the child associated with the allocation belongs to the family
    allocation_child_id = allocation.google_sheets_child_id
    child_rows = get_children()
    family_children = get_family_children(family_id, child_rows)

    associated_child = None
    for child in family_children:
        if child.get(ChildColumnNames.ID) == allocation_child_id:
            associated_child = child
            break

    if not associated_child:
        return jsonify({"error": "Child not associated with the authenticated family."}), 403

    # Check if the provider is associated with the child
    provider_child_mapping_rows = get_provider_child_mappings()
    provider_rows = get_providers()
    child_providers = get_child_providers(allocation_child_id, provider_child_mapping_rows, provider_rows)

    provider_found = False
    provider_data = None
    for provider in child_providers:
        if provider.get(ProviderColumnNames.ID) == provider_id:
            provider_found = True
            provider_data = provider
            break

    if not provider_found:
        return jsonify({"error": "Provider not associated with the specified child."}), 403

    if not provider_data or not provider_data.get(ProviderColumnNames.PAYMENT_ENABLED):
        return jsonify({"error": "Cannot submit: provider payment not enabled"}), 400

    family_data = get_family(family_id, get_families())
    if not family_data.get(FamilyColumnNames.PAYMENT_ENABLED):
        return jsonify({"error": "Cannot submit: family payment not enabled"}), 400

    try:
        lump_sum = AllocatedLumpSum.create_lump_sum(
            allocation=allocation,
            provider_id=provider_id,
            amount_cents=amount_cents,
            hours=hours,
        )
        db.session.add(lump_sum)
        db.session.commit()
        send_lump_sum_payment_request_email(
            provider_name=provider.get(ProviderColumnNames.NAME),
            google_sheets_provider_id=provider_id,
            child_first_name=associated_child.get(ChildColumnNames.FIRST_NAME),
            child_last_name=associated_child.get(ChildColumnNames.LAST_NAME),
            google_sheets_child_id=allocation_child_id,
            amount_in_cents=amount_cents,
            hours=hours,
            month=allocation.date.strftime("%B %Y"),
        )
        return (
            AllocatedLumpSumResponse.model_validate(lump_sum).model_dump_json(),
            201,
            {"Content-Type": "application/json"},
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
