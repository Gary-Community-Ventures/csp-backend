from flask import Blueprint

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_family_user, get_provider_user
from app.constants import UNKNOWN
from app.models import MonthAllocation, Payment, ProviderPaymentSettings
from app.schemas.payment import (
    FamilyPaymentHistoryItem,
    FamilyPaymentHistoryResponse,
    ProviderPaymentHistoryItem,
    ProviderPaymentHistoryResponse,
)
from app.supabase.helpers import cols, format_name, unwrap_or_abort
from app.supabase.tables import Child, Family, Provider

bp = Blueprint("payments", __name__)


@bp.get("/family/payments")
@auth_required(ClerkUserType.FAMILY)
def get_family_payment_history():
    """Get payment history for the authenticated family's children."""
    user = get_family_user()
    family_id = user.user_data.family_id

    children_results = Child.select_by_family_id(
        cols(Child.ID, Child.FIRST_NAME, Child.LAST_NAME, Family.join(Family.ID), Provider.join(Provider.NAME)),
        int(family_id),
    ).execute()
    children = unwrap_or_abort(children_results)

    if len(children) == 0:
        return (
            FamilyPaymentHistoryResponse(payments=[], total_count=0, total_amount_cents=0).model_dump_json(),
            200,
            {"Content-Type": "application/json"},
        )

    child_ids = [Child.ID(c) for c in children]

    # Query payments for these children, ordered by newest first
    payments: list[Payment] = (
        Payment.query.filter(Payment.child_supabase_id.in_(child_ids)).order_by(Payment.created_at.desc()).all()
    )

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

        child = Child.find_by_id(children, payment.child_supabase_id)
        provider = Provider.find_by_id(Provider.unwrap(child), payment.provider_supabase_id) if child is not None else None

        child_name = format_name(child)
        provider_name = provider.NAME if provider is not None else UNKNOWN

        # Get month from allocation
        month_allocation = MonthAllocation.query.get(payment.month_allocation_id)
        month_str = month_allocation.date.strftime("%Y-%m-%d") if month_allocation else UNKNOWN

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
                provider_id=payment.provider_supabase_id,
                child_name=child_name,
                child_id=payment.child_supabase_id,
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
    provider_settings = ProviderPaymentSettings.query.filter_by(provider_supabase_id=provider_id).first()

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
    payments: list[Payment] = (
        Payment.query.filter(Payment.provider_payment_settings_id == provider_settings.id)
        .order_by(Payment.created_at.desc())
        .all()
    )

    provider_results = Provider.select_by_id(
        cols(Provider.ID, Child.join(Child.FIRST_NAME, Child.LAST_NAME)), int(provider_id)
    ).execute()
    provider = unwrap_or_abort(provider_results)

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

        child = Child.find_by_id(Child.unwrap(provider), payment.child_supabase_id)
        child_name = format_name(child)

        # Get month from allocation
        month_allocation = MonthAllocation.query.get(payment.month_allocation_id)
        month_str = month_allocation.date.strftime("%Y-%m-%d") if month_allocation else UNKNOWN

        # Get payment method used for this payment
        payment_method = UNKNOWN
        if payment.successful_attempt:
            # Get the payment method from the first attempt (they should all be the same)
            payment_method = (
                payment.successful_attempt.payment_method.value
                if payment.successful_attempt.payment_method
                else UNKNOWN
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
                child_id=payment.child_supabase_id,
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
