import os
from datetime import datetime
from collections import defaultdict

from app import create_app
from datetime import datetime
from app.models import AllocatedCareDay, PaymentRequest, MonthAllocation
from app.extensions import db
from app.sheets.mappings import (
    get_provider,
    get_child,
    get_children,
    get_providers,
    ProviderColumnNames,
    ChildColumnNames,
)


# Create Flask app context
app = create_app()
app.app_context().push()


def run_payment_requests():
    print("Starting payment request processing...")

    # Query for submitted and unprocessed care days
    care_days_to_process = (
        AllocatedCareDay.query.join(MonthAllocation)
        .filter(
            AllocatedCareDay.last_submitted_at.isnot(None),
            AllocatedCareDay.payment_distribution_requested == False,
            AllocatedCareDay.deleted_at.is_(None),
            AllocatedCareDay.locked_date <= datetime.utcnow(),
        )
        .all()
    )

    if not care_days_to_process:
        print("No submitted and unprocessed care days found.")
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
        total_hours = sum(day.day_count for day in days)

        provider_data = get_provider(provider_id, all_providers_data)
        child_data = get_child(child_id, all_children_data)

        if not provider_data:
            print(
                f"Skipping payment request for provider ID {provider_id}: Provider not found in Google Sheets."
            )
            continue
        if not child_data:
            print(
                f"Skipping payment request for child ID {child_id}: Child not found in Google Sheets."
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

        # Mark care days as payment_distribution_requested
        for day in days:
            day.payment_distribution_requested = True

    db.session.commit()
    print("Payment request processing finished.")


if __name__ == "__main__":
    run_payment_requests()
