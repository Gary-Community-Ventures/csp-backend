from datetime import date

from flask import Blueprint, current_app, jsonify, request

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.models import AllocatedCareDay, MonthAllocation
from app.schemas.care_day import AllocatedCareDayResponse
from app.schemas.month_allocation import (
    MonthAllocationResponse,
)
from app.schemas.payment import PaymentErrorResponse, PaymentProcessedResponse
from app.sheets.mappings import get_child, get_children, get_provider, get_providers
from app.utils.email_service import (
    send_care_days_payment_request_email,
)
from app.utils.json_utils import custom_jsonify

bp = Blueprint("child", __name__)


@bp.route(
    "/child/<string:child_id>/allocation/<int:month>/<int:year>",
    methods=["GET"],
)
@auth_required(ClerkUserType.FAMILY)
def get_month_allocation(child_id, month, year):
    provider_id = request.args.get("provider_id")
    try:
        month_date = date(year, month, 1)
        allocation = MonthAllocation.get_for_month(child_id, month_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    if not allocation:
        return jsonify({"error": "Allocation not found"}), 400

    if provider_id:
        care_days_query = AllocatedCareDay.query.filter_by(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=provider_id,
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


@bp.route(
    "/child/<string:child_id>/provider/<string:provider_id>/allocation/<int:month>/<int:year>/submit",
    methods=["POST"],
)
@auth_required(ClerkUserType.FAMILY)
def submit_care_days(child_id, provider_id, month, year):
    try:
        month_date = date(year, month, 1)
    except ValueError:
        return jsonify({"error": "Invalid month or year"}), 400

    allocation = MonthAllocation.query.filter_by(google_sheets_child_id=child_id, date=month_date).first()
    if not allocation:
        return jsonify({"error": "Allocation not found"}), 404

    if allocation.over_allocation:
        return jsonify({"error": "Cannot submit: allocation exceeded"}), 400

    care_days_to_submit = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_google_sheets_id == provider_id,
        AllocatedCareDay.deleted_at.is_(None),  # Don't submit deleted days
        AllocatedCareDay.last_submitted_at.is_(None),  # Don't submit already submitted days
    ).all()

    # Only process payment for care days that have an amount
    if not care_days_to_submit:
        return jsonify({"error": "No care days to submit"}), 400

    # Get provider and child data for payment processing and email
    all_providers_data = get_providers()
    all_children_data = get_children()

    provider_data = get_provider(provider_id, all_providers_data)
    child_data = get_child(child_id, all_children_data)

    if not provider_data:
        return jsonify({"error": "Provider not found"}), 404
    if not child_data:
        return jsonify({"error": "Child not found"}), 404

    # Calculate total amount for email (before payment processing)
    total_amount_cents = sum(day.amount_cents for day in care_days_to_submit)

    # Process payment for submitted care days
    # PaymentService now handles marking care days as submitted within the same transaction
    payment_successful = current_app.payment_service.process_payment(
        external_provider_id=provider_id,
        external_child_id=child_id,
        month_allocation=allocation,
        allocated_care_days=care_days_to_submit,
    )

    if not payment_successful:
        error_response = PaymentErrorResponse(error="Payment processing failed. Please try again.")
        return error_response.model_dump_json(), 500, {"Content-Type": "application/json"}

    # Send payment notification email (after successful payment)
    # If email fails, we log it but don't fail the request since payment succeeded
    try:
        send_care_days_payment_request_email(
            provider_name=provider_data.get("Name", "Unknown"),
            google_sheets_provider_id=provider_id,
            child_first_name=child_data.get("First Name", "Unknown"),
            child_last_name=child_data.get("Last Name", ""),
            google_sheets_child_id=child_id,
            amount_in_cents=total_amount_cents,
            care_days=care_days_to_submit,
        )
    except Exception as email_error:
        # Log email failure as warning, but payment was successful so continue
        current_app.logger.warning(
            f"Payment processed successfully for provider {provider_id}, child {child_id} "
            f"(${total_amount_cents / 100:.2f}), but email notification failed: {email_error}"
        )

    response = PaymentProcessedResponse(
        message="Payment processed successfully",
        total_amount=f"${total_amount_cents / 100:.2f}",
        care_days=[AllocatedCareDayResponse.model_validate(day) for day in care_days_to_submit],
    )

    return response.model_dump_json(), 200, {"Content-Type": "application/json"}
