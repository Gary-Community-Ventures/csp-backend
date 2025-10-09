from datetime import date

from flask import Blueprint, abort, current_app, jsonify, request

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.auth.helpers import get_family_user
from app.models import AllocatedCareDay, MonthAllocation
from app.schemas.care_day import AllocatedCareDayResponse
from app.schemas.month_allocation import (
    MonthAllocationResponse,
)
from app.schemas.payment import PaymentErrorResponse, PaymentProcessedResponse
from app.supabase.helpers import UnwrapError, cols, unwrap_or_abort
from app.supabase.tables import Child, Provider
from app.utils.email.senders import send_care_days_payment_email
from app.utils.json_utils import custom_jsonify

bp = Blueprint("child", __name__)


@bp.get("/child/<string:child_id>/allocation/<int:month>/<int:year>")
@auth_required(ClerkUserType.FAMILY)
def get_month_allocation(child_id, month, year):
    user = get_family_user()
    family_id = user.user_data.family_id

    child_results = Child.select_by_id(cols(Child.ID, Child.FAMILY_ID), int(child_id)).execute()
    child = unwrap_or_abort(child_results)

    if Child.FAMILY_ID(child) != family_id:
        return jsonify({"error": "Child not found"}), 404

    try:
        month_date = date(year, month, 1)
        allocation = MonthAllocation.get_for_month(child_id, month_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not allocation:
        return jsonify({"error": "Allocation not found"}), 400

    provider_id = request.args.get("provider_id")
    if provider_id:
        care_days_query = AllocatedCareDay.query.filter_by(
            care_month_allocation_id=allocation.id,
            provider_supabase_id=provider_id,
        )
    else:
        care_days_query = AllocatedCareDay.query.filter_by(care_month_allocation_id=allocation.id)
    care_days = care_days_query.all()

    # Serialize care_days using Pydantic model
    serialized_care_days = []
    for day in care_days:
        care_day_data = AllocatedCareDayResponse.model_validate(day).model_dump()
        serialized_care_days.append(care_day_data)

    # Serialize allocation using MonthAllocationResponse
    serialized_allocation = MonthAllocationResponse.model_validate(allocation).model_dump()
    serialized_allocation["care_days"] = serialized_care_days

    return custom_jsonify(serialized_allocation)


@bp.post("/child/<string:child_id>/provider/<string:provider_id>/allocation/<int:month>/<int:year>/submit")
@auth_required(ClerkUserType.FAMILY)
def submit_care_days(child_id, provider_id, month, year):
    user = get_family_user()
    family_id = user.user_data.family_id
    child_results = Child.select_by_id(
        cols(
            Child.ID,
            Child.FAMILY_ID,
            Child.PAYMENT_ENABLED,
            Child.FIRST_NAME,
            Child.LAST_NAME,
            Provider.join(Provider.ID, Provider.PAYMENT_ENABLED, Provider.NAME, Provider.TYPE),
        ),
        int(child_id),
    ).execute()
    child = unwrap_or_abort(child_results)

    if child is None or Child.FAMILY_ID(child) != family_id:
        return jsonify({"error": "Child not found"}), 404

    if not Child.PAYMENT_ENABLED(child):
        return jsonify({"error": "Cannot submit: child payment not enabled"}), 400

    provider = Provider.find_by_id(Provider.unwrap(child), provider_id)

    if provider is None:
        return jsonify({"error": "Provider not found"}), 404

    if not Provider.PAYMENT_ENABLED(provider):
        return jsonify({"error": "Cannot submit: provider payment not enabled"}), 400

    try:
        month_date = date(year, month, 1)
    except ValueError:
        return jsonify({"error": "Invalid month or year"}), 400

    allocation = MonthAllocation.query.filter_by(child_supabase_id=child_id, date=month_date).first()
    if not allocation:
        return jsonify({"error": "Allocation not found"}), 404

    if allocation.selected_over_allocation:
        return jsonify({"error": "Cannot submit: allocation exceeded"}), 400

    care_days_to_submit = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_supabase_id == provider_id,
        AllocatedCareDay.deleted_at.is_(None),  # Don't submit deleted days
        AllocatedCareDay.last_submitted_at.is_(None),  # Don't submit already submitted days
    ).all()

    # Only process payment for care days that have an amount
    if not care_days_to_submit:
        return jsonify({"error": "No care days to submit"}), 400

    # Calculate total amount for email (before payment processing)
    total_amount_cents = sum(day.amount_cents for day in care_days_to_submit)

    # Process payment for submitted care days
    # PaymentService now handles marking care days as submitted within the same transaction
    try:
        payment_successful = current_app.payment_service.process_payment(
            provider_id=provider_id,
            child_id=child_id,
            provider_type=Provider.TYPE(provider),
            month_allocation=allocation,
            allocated_care_days=care_days_to_submit,
        )
    except UnwrapError:
        abort(502, description="Database query failed")

    if not payment_successful:
        error_response = PaymentErrorResponse(error="Payment processing failed. Please try again.")
        return error_response.model_dump_json(), 500, {"Content-Type": "application/json"}

    # Send payment notification email (after successful payment)
    # TODO: leave so whe know when payments happen but remove in future
    send_care_days_payment_email(
        provider_name=Provider.NAME(provider),
        provider_id=provider_id,
        child_first_name=Child.FIRST_NAME(child),
        child_last_name=Child.LAST_NAME(child),
        child_id=child_id,
        amount_in_cents=total_amount_cents,
        care_days=care_days_to_submit,
    )

    response = PaymentProcessedResponse(
        message="Payment processed successfully",
        total_amount=f"${total_amount_cents / 100:.2f}",
        care_days=[AllocatedCareDayResponse.model_validate(day) for day in care_days_to_submit],
    )

    return response.model_dump_json(), 200, {"Content-Type": "application/json"}
