from flask import Blueprint

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_family_user, get_provider_user
from app.models import MonthAllocation, Payment, ProviderPaymentSettings
from app.schemas.payment import (
    FamilyPaymentHistoryItem,
    FamilyPaymentHistoryResponse,
    ProviderPaymentHistoryItem,
    ProviderPaymentHistoryResponse,
)
from app.sheets.helpers import format_name
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_family_children,
    get_provider,
    get_providers,
)

bp = Blueprint("payments", __name__)


@bp.get("/family/payments")
@auth_required(ClerkUserType.FAMILY)
def get_family_payment_history():
    """Get payment history for the authenticated family's children."""
    user = get_family_user()
    family_id = user.user_data.family_id

    # Get all children for this family
    all_children_data = get_children()
    family_children = get_family_children(family_id, all_children_data)

    if not family_children:
        return (
            FamilyPaymentHistoryResponse(payments=[], total_count=0, total_amount_cents=0).model_dump_json(),
            200,
            {"Content-Type": "application/json"},
        )

    # Get child IDs for this family
    family_child_ids = [child.get(ChildColumnNames.ID) for child in family_children]

    # Query payments for these children, ordered by newest first
    payments = (
        Payment.query.filter(Payment.external_child_id.in_(family_child_ids)).order_by(Payment.created_at.desc()).all()
    )

    # Get provider data for names
    all_providers_data = get_providers()

    # Build response
    payment_items = []
    total_amount = 0

    for payment in payments:
        # Get payment status from latest attempt
        payment_status = "pending"
        if payment.has_successful_attempt:
            payment_status = "success"
        elif payment.has_failed_attempt:
            payment_status = "failed"

        # Get provider name
        provider_data = get_provider(payment.external_provider_id, all_providers_data)
        provider_name = provider_data.get(ProviderColumnNames.NAME) if provider_data else "Unknown Provider"

        # Get child name
        child_data = next((c for c in family_children if c.get(ChildColumnNames.ID) == payment.external_child_id), None)
        child_name = format_name(child_data) if child_data else "Unknown Child"

        # Get month from allocation
        month_allocation = MonthAllocation.query.get(payment.month_allocation_id)
        month_str = month_allocation.date.strftime("%Y-%m-%d") if month_allocation else "Unknown"

        # Determine payment type
        payment_type = (
            "care_days" if payment.allocated_care_days else "lump_sum" if payment.allocated_lump_sums else "other"
        )

        payment_items.append(
            FamilyPaymentHistoryItem(
                payment_id=str(payment.id),
                created_at=payment.created_at.isoformat() if payment.created_at else "",
                amount_cents=payment.amount_cents,
                status=payment_status,
                provider_name=provider_name,
                provider_id=payment.external_provider_id,
                child_name=child_name,
                child_id=payment.external_child_id,
                month=month_str,
                payment_type=payment_type,
            )
        )

        total_amount += payment.amount_cents

    response = FamilyPaymentHistoryResponse(
        payments=payment_items, total_count=len(payment_items), total_amount_cents=total_amount
    )

    return response.model_dump_json(), 200, {"Content-Type": "application/json"}


@bp.get("/provider/payments")
@auth_required(ClerkUserType.PROVIDER)
def get_provider_payment_history():
    """Get payment history for the authenticated provider."""
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    # Get provider payment settings to get the internal provider ID
    provider_settings = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()

    if not provider_settings:
        # No payment settings means no payments
        return (
            ProviderPaymentHistoryResponse(
                payments=[], total_count=0, total_amount_cents=0, successful_payments_cents=0
            ).model_dump_json(),
            200,
            {"Content-Type": "application/json"},
        )

    # Query payments for this provider, ordered by newest first
    payments = (
        Payment.query.filter(Payment.provider_payment_settings_id == provider_settings.id)
        .order_by(Payment.created_at.desc())
        .all()
    )

    # Get child and family data for names
    all_children_data = get_children()

    # Build response
    payment_items = []
    total_amount = 0
    successful_amount = 0

    for payment in payments:
        # Get payment status from latest attempt
        payment_status = "pending"
        if payment.has_successful_attempt:
            payment_status = "success"
            successful_amount += payment.amount_cents
        elif payment.has_failed_attempt:
            payment_status = "failed"

        # Get child name
        child_data = get_child(payment.external_child_id, all_children_data)
        child_name = format_name(child_data) if child_data else "Unknown Child"

        # Get month from allocation
        month_allocation = MonthAllocation.query.get(payment.month_allocation_id)
        month_str = month_allocation.date.strftime("%Y-%m-%d") if month_allocation else "Unknown"

        # Get payment method used for this payment
        payment_method = "unknown"
        if payment.successful_attempt:
            # Get the payment method from the first attempt (they should all be the same)
            payment_method = (
                payment.successful_attempt.payment_method.value
                if payment.successful_attempt.payment_method
                else "unknown"
            )

        # Determine payment type
        payment_type = (
            "care_days" if payment.allocated_care_days else "lump_sum" if payment.allocated_lump_sums else "other"
        )

        payment_items.append(
            ProviderPaymentHistoryItem(
                payment_id=str(payment.id),
                created_at=payment.created_at.isoformat() if payment.created_at else "",
                amount_cents=payment.amount_cents,
                status=payment_status,
                child_name=child_name,
                child_id=payment.external_child_id,
                month=month_str,
                payment_method=payment_method,
                payment_type=payment_type,
            )
        )

        total_amount += payment.amount_cents

    response = ProviderPaymentHistoryResponse(
        payments=payment_items,
        total_count=len(payment_items),
        total_amount_cents=total_amount,
        successful_payments_cents=successful_amount,
    )

    return response.model_dump_json(), 200, {"Content-Type": "application/json"}
