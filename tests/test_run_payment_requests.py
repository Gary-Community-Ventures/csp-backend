from datetime import date, datetime, timedelta, timezone

import pytest

from app.enums.care_day_type import CareDayType
from app.extensions import db
from app.models import (
    AllocatedCareDay,
    FamilyPaymentSettings,
    MonthAllocation,
    PaymentRate,
    ProviderPaymentSettings,
)
from app.scripts.run_payment_requests import run_payment_requests


@pytest.fixture
def setup_payment_request_data(app):
    with app.app_context():
        # Create a MonthAllocation
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=1000000,
            child_supabase_id="101",
        )
        db.session.add(allocation)
        db.session.commit()

        # Create PaymentRates for testing
        payment_rate_1 = PaymentRate(
            provider_supabase_id="201",
            child_supabase_id="101",
            full_day_rate_cents=60000,
            half_day_rate_cents=30000,
        )
        payment_rate_2 = PaymentRate(
            provider_supabase_id="202",
            child_supabase_id="101",
            full_day_rate_cents=70000,
            half_day_rate_cents=35000,
        )
        db.session.add_all([payment_rate_1, payment_rate_2])

        # Create ProviderPaymentSettings for the providers
        provider_settings_1 = ProviderPaymentSettings.new("201")
        provider_settings_2 = ProviderPaymentSettings.new("202")
        db.session.add_all([provider_settings_1, provider_settings_2])

        # Create FamilyPaymentSettings for the family (assuming family_id is "family123" based on the child)
        family_settings = FamilyPaymentSettings.new("family123")
        family_settings.chek_wallet_balance = 1000000  # Set a high balance so payment doesn't fail
        db.session.add(family_settings)

        db.session.commit()

        # Create submitted care days for processing
        # Use a date from last week so its locked_date (Monday 23:59:59) is in the past
        # We create directly instead of using create_care_day since that prevents past dates
        care_day_1 = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="201",
            date=date.today() - timedelta(days=7),
            type=CareDayType.FULL_DAY,
            amount_cents=60000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=5),
            payment_distribution_requested=False,
        )
        db.session.add(care_day_1)

        # Use another date from last week
        care_day_2 = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="201",
            date=date.today() - timedelta(days=6),
            type=CareDayType.HALF_DAY,
            amount_cents=40000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=4),
            payment_distribution_requested=False,
        )
        db.session.add(care_day_2)

        # Care day for a different provider/child that should NOT be processed by this run
        # Use a date from last week so it's locked
        care_day_3 = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="202",
            date=date.today() - timedelta(days=5),
            type=CareDayType.FULL_DAY,
            amount_cents=60000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=3),
            payment_distribution_requested=False,
        )
        db.session.add(care_day_3)

        # Care day that is already processed
        care_day_4 = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="201",
            date=date.today() - timedelta(days=4),
            type=CareDayType.FULL_DAY,
            amount_cents=60000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
            payment_distribution_requested=True,
        )
        db.session.add(care_day_4)
        db.session.commit()

        # Care day that is submitted but not yet locked (locked_date in future)
        future_date = date.today() + timedelta(days=7)  # A week from now
        care_day_5 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="201",
            care_date=future_date,
            day_type=CareDayType.FULL_DAY,
        )
        care_day_5.last_submitted_at = datetime.now(timezone.utc) - timedelta(days=1)  # Submitted yesterday
        care_day_5.payment_distribution_requested = False

        db.session.add_all([care_day_1, care_day_2, care_day_3, care_day_4, care_day_5])
        db.session.commit()

        yield allocation, care_day_1, care_day_2, care_day_3, care_day_4, care_day_5


def test_run_payment_requests_script(app, setup_payment_request_data, mocker):
    allocation, care_day_1, care_day_2, care_day_3, care_day_4, care_day_5 = setup_payment_request_data

    # Mock the payment service process_payment method
    mock_payment_service = mocker.patch(
        "app.scripts.run_payment_requests.payment_service.process_payment", return_value=True
    )

    # Mock child and provider data lookup functions
    mocker.patch("app.scripts.run_payment_requests.get_child_name", return_value=("Test", "Child"))
    mocker.patch("app.scripts.run_payment_requests.get_provider_name", return_value="Test Provider")
    mocker.patch("app.scripts.run_payment_requests.get_family_id_from_child", return_value="family123")

    # Run the script
    run_payment_requests()

    # Verify that the payment service was called BEFORE refreshing objects
    assert mock_payment_service.call_count == 2

    # Get the actual calls to check what was passed
    calls = mock_payment_service.call_args_list

    # Check that both provider groups were processed
    provider_ids_called = {call.kwargs["provider_supabase_id"] for call in calls}
    assert provider_ids_called == {"201", "202"}

    # Check each call has the expected structure
    for call in calls:
        kwargs = call.kwargs
        assert "provider_supabase_id" in kwargs
        assert "child_supabase_id" in kwargs
        assert kwargs["child_supabase_id"] == "101"
        assert "month_allocation" in kwargs
        assert kwargs["month_allocation"] == allocation
        assert "allocated_care_days" in kwargs
        assert len(kwargs["allocated_care_days"]) > 0

        # Check the specific provider calls
        if kwargs["provider_supabase_id"] == "201":
            # Should have 3 care days for provider 201
            assert len(kwargs["allocated_care_days"]) == 3
            care_day_ids = {day.id for day in kwargs["allocated_care_days"]}
            assert care_day_ids == {care_day_1.id, care_day_2.id, care_day_5.id}
        elif kwargs["provider_supabase_id"] == "202":
            # Should have 1 care day for provider 202
            assert len(kwargs["allocated_care_days"]) == 1
            assert kwargs["allocated_care_days"][0].id == care_day_3.id

    with app.app_context():
        # NOW refresh the objects from the database to get the latest state
        db.session.expire_all()

        # Verify care days were marked as processed
        processed_care_day_1 = db.session.get(AllocatedCareDay, care_day_1.id)
        processed_care_day_2 = db.session.get(AllocatedCareDay, care_day_2.id)
        processed_care_day_3 = db.session.get(AllocatedCareDay, care_day_3.id)
        already_processed_care_day_4 = db.session.get(AllocatedCareDay, care_day_4.id)

        assert processed_care_day_1.payment_distribution_requested is True
        assert processed_care_day_2.payment_distribution_requested is True
        assert processed_care_day_3.payment_distribution_requested is True
        assert already_processed_care_day_4.payment_distribution_requested is True
