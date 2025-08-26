from collections import defaultdict
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation, PaymentRequest, ProviderPaymentSettings
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_provider,
    get_providers,
)
from app.utils.email_service import send_care_days_payment_request_email
from app.services.payment_service import PaymentService

# Create Flask app context
app = create_app()
app.app_context().push()

# Initialize PaymentService within the app context
payment_service = PaymentService(app)


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
                f"run_payment_requests: Skipping payment for provider ID {provider_id}: Provider not found in Google Sheets."
            )
            continue
        if not child_data:
            app.logger.warning(
                f"run_payment_requests: Skipping payment for child ID {child_id}: Child not found in Google Sheets."
            )
            continue

        # Retrieve the ProviderPaymentSettings object
        provider_orm = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()
        if not provider_orm:
            app.logger.warning(
                f"run_payment_requests: Skipping payment for provider ID {provider_id}: Provider not found in database."
            )
            continue

        # Process payment using the PaymentService
        payment_successful = payment_service.process_payment(
            provider=provider_orm,
            allocated_care_days=days,
            external_provider_id=provider_id,
            external_child_id=child_id,
        )

        if payment_successful:
            # Mark care days as payment_distribution_requested only if payment was successful
            for day in days:
                day.payment_distribution_requested = True
        else:
            app.logger.error(
                f"run_payment_requests: Failed to process payment for provider {provider_id} and child {child_id}."
            )

    db.session.commit()
    app.logger.info("run_payment_requests: Payment processing finished.")


if __name__ == "__main__":
    run_payment_requests()
