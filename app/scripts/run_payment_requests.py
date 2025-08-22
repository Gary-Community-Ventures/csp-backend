from collections import defaultdict
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation, PaymentRequest
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_provider,
    get_providers,
)
from app.utils.email_service import send_care_days_payment_request_email

# Create Flask app context
app = create_app()
app.app_context().push()


def run_payment_requests():
    app.logger.info("run_payment_requests: Starting payment request processing...")

    # Query for submitted and unprocessed care days
    care_days_to_process = (
        AllocatedCareDay.query.join(MonthAllocation)
        .filter(
            AllocatedCareDay.last_submitted_at.isnot(None),
            AllocatedCareDay.payment_distribution_requested.is_(False),
            AllocatedCareDay.deleted_at.is_(None),
            AllocatedCareDay.locked_date <= datetime.now(timezone.utc),
        )
        .all()
    )

    if not care_days_to_process:
        app.logger.warning("run_payment_requests: No submitted and unprocessed care days found.")
        return

    # Group care days by provider and child
    grouped_care_days = defaultdict(list)
    for day in care_days_to_process:
        grouped_care_days[
            (
                day.provider_google_sheets_id,
                day.care_month_allocation.google_sheets_child_id,
            )
        ].append(day)

    all_children_data = get_children()
    all_providers_data = get_providers()

    for (provider_id, child_id), days in grouped_care_days.items():
        total_amount_cents = sum(day.amount_cents for day in days)

        provider_data = get_provider(provider_id, all_providers_data)
        child_data = get_child(child_id, all_children_data)

        if not provider_data:
            app.logger.warning(
                f"run_payment_requests: Skipping payment request for provider ID {provider_id}: Provider not found in Google Sheets."
            )
            continue
        if not child_data:
            app.logger.warning(
                f"run_payment_requests: Skipping payment request for child ID {child_id}: Child not found in Google Sheets."
            )
            continue

        provider_name = (
            provider_data.get(ProviderColumnNames.NAME)
            or f"{provider_data.get(ProviderColumnNames.FIRST_NAME)} {provider_data.get(ProviderColumnNames.LAST_NAME)}"
        )
        child_first_name = child_data.get(ChildColumnNames.FIRST_NAME)
        child_last_name = child_data.get(ChildColumnNames.LAST_NAME)

        # Create PaymentRequest record
        payment_request = PaymentRequest(
            google_sheets_provider_id=provider_id,
            google_sheets_child_id=child_id,
            care_days_count=len(days),
            amount_in_cents=total_amount_cents,
            care_day_ids=[day.id for day in days],
        )
        db.session.add(payment_request)

        # TODO Write payment request information to a spreadsheet for James
        sent_email = send_care_days_payment_request_email(
            provider_name=provider_name,
            google_sheets_provider_id=provider_id,
            child_first_name=child_first_name,
            child_last_name=child_last_name,
            google_sheets_child_id=child_id,
            amount_in_cents=total_amount_cents,
            care_days=days,
        )
        if not sent_email:
            app.logger.error(
                f"run_payment_requests: Failed to send payment request email for provider {provider_name} (ID: {provider_id}) and child {child_first_name} {child_last_name} (ID: {child_id})."
            )
            payment_request.is_email_sent = False
            continue

        # Mark care days as payment_distribution_requested
        for day in days:
            day.payment_distribution_requested = True

    db.session.commit()
    app.logger.info("run_payment_requests: Payment request processing finished.")


if __name__ == "__main__":
    run_payment_requests()
