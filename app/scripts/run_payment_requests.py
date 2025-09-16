from collections import defaultdict

from app import create_app
from app.extensions import db
from app.models import (
    AllocatedCareDay,
    MonthAllocation,
    ProviderPaymentSettings,
)
from app.services.payment.payment_service import PaymentService
from app.supabase.helpers import cols
from app.supabase.tables import Child, Provider

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
            AllocatedCareDay.payment_id.is_(None),
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
                day.provider_supabase_id,
                day.care_month_allocation.child_supabase_id,
            )
        ].append(day)

    children = Child.query().select(cols(Child.ID)).execute()
    providers = Provider.query().select(cols(Provider.ID)).execute()
    child_ids = set([c.id for c in children])
    provider_ids = set([p.id for p in providers])

    for (provider_id, child_id), days in grouped_care_days.items():
        if provider_id not in provider_ids:
            app.logger.warning(
                f"run_payment_requests: Skipping payment for provider ID {provider_id}: Provider not found"
            )
            continue
        if child_id not in child_ids:
            app.logger.warning(f"run_payment_requests: Skipping payment for child ID {child_id}: Child not found")
            continue

        # Retrieve the ProviderPaymentSettings object
        provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()
        if not provider_payment_settings:
            app.logger.warning(
                f"run_payment_requests: Skipping payment for provider ID {provider_id}: Provider not found in database."
            )
            continue

        # Process payment using the PaymentService
        month_allocation = days[0].care_month_allocation  # All care days belong to same month allocation
        payment_successful = payment_service.process_payment(
            external_provider_id=provider_id,
            external_child_id=child_id,
            month_allocation=month_allocation,
            allocated_care_days=days,
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
