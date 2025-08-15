from datetime import date, datetime, timedelta

import pytest

from app.enums.care_day_type import CareDayType
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation, PaymentRate, PaymentRequest
from app.sheets.mappings import ChildColumnNames, KeyMap, ProviderColumnNames
from run_payment_requests import run_payment_requests


@pytest.fixture
def setup_payment_request_data(app):
    with app.app_context():
        # Create a MonthAllocation
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=1000000,
            google_sheets_child_id="101",
        )
        db.session.add(allocation)
        db.session.commit()

        # Create PaymentRates for testing
        payment_rate_1 = PaymentRate(
            google_sheets_provider_id="201",
            google_sheets_child_id="101",
            full_day_rate_cents=60000,
            half_day_rate_cents=30000,
        )
        payment_rate_2 = PaymentRate(
            google_sheets_provider_id="202",
            google_sheets_child_id="101",
            full_day_rate_cents=70000,
            half_day_rate_cents=35000,
        )
        db.session.add_all([payment_rate_1, payment_rate_2])
        db.session.commit()

        # Create submitted care days for processing
        care_day_1 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="201",
            care_date=date.today() + timedelta(days=10),
            day_type=CareDayType.FULL_DAY,
        )
        care_day_1.last_submitted_at = datetime.utcnow() - timedelta(days=5)
        care_day_1.payment_distribution_requested = False
        care_day_1.locked_date = datetime.utcnow() - timedelta(days=1)

        care_day_2 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="201",
            care_date=date.today() + timedelta(days=11),
            day_type=CareDayType.HALF_DAY,
        )
        care_day_2.last_submitted_at = datetime.utcnow() - timedelta(days=4)
        care_day_2.payment_distribution_requested = False
        care_day_2.locked_date = datetime.utcnow() - timedelta(days=1)

        # Care day for a different provider/child that should NOT be processed by this run
        care_day_3 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="202",
            care_date=date.today() + timedelta(days=12),
            day_type=CareDayType.FULL_DAY,
        )
        care_day_3.last_submitted_at = datetime.utcnow() - timedelta(days=3)
        care_day_3.payment_distribution_requested = False
        care_day_3.locked_date = datetime.utcnow() - timedelta(days=1)

        # Care day that is already processed
        care_day_4 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="201",
            care_date=date.today() + timedelta(days=13),
            day_type=CareDayType.FULL_DAY,
        )
        care_day_4.last_submitted_at = datetime.utcnow() - timedelta(days=2)
        care_day_4.payment_distribution_requested = True

        # Care day that is submitted but not yet locked (locked_date in future)
        future_date = date.today() + timedelta(days=7)  # A week from now
        care_day_5 = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id="201",
            care_date=future_date,
            day_type=CareDayType.FULL_DAY,
        )
        care_day_5.last_submitted_at = datetime.utcnow() - timedelta(days=1)  # Submitted yesterday
        care_day_5.payment_distribution_requested = False

        db.session.add_all([care_day_1, care_day_2, care_day_3, care_day_4, care_day_5])
        db.session.commit()

        yield allocation, care_day_1, care_day_2, care_day_3, care_day_4, care_day_5


def test_run_payment_requests_script(app, setup_payment_request_data, mocker):
    _, care_day_1, care_day_2, care_day_3, care_day_4, care_day_5 = setup_payment_request_data

    # Mock external dependencies
    mocker.patch.dict("os.environ", {"GOOGLE_SHEETS_CREDENTIALS": '{"type": "service_account"}'})
    mocker.patch(
        "run_payment_requests.get_children",
        return_value=[
            KeyMap(
                {
                    ChildColumnNames.ID.key: "101",
                    ChildColumnNames.FIRST_NAME.key: "Test",
                    ChildColumnNames.LAST_NAME.key: "Child",
                }
            )
        ],
    )
    mocker.patch(
        "run_payment_requests.get_providers",
        return_value=[
            KeyMap(
                {
                    ProviderColumnNames.ID.key: "201",
                    ProviderColumnNames.NAME.key: "Test Provider",
                }
            ),
            KeyMap(
                {
                    ProviderColumnNames.ID.key: "202",
                    ProviderColumnNames.NAME.key: "Another Provider",
                }
            ),
        ],
    )
    mocker.patch(
        "run_payment_requests.get_child",
        side_effect=lambda child_id, children: next(
            (c for c in children if c.get(ChildColumnNames.ID) == child_id), None
        ),
    )
    mocker.patch(
        "run_payment_requests.get_provider",
        side_effect=lambda provider_id, providers: next(
            (p for p in providers if p.get(ProviderColumnNames.ID) == provider_id), None
        ),
    )
    mock_send_email = mocker.patch("run_payment_requests.send_care_days_payment_request_email", return_value=True)

    # Run the script
    run_payment_requests()

    with app.app_context():
        # Refresh the objects from the database to get the latest state
        db.session.expire_all()

        # Verify PaymentRequest was created
        payment_requests = PaymentRequest.query.order_by(PaymentRequest.google_sheets_provider_id).all()
        assert len(payment_requests) == 2

        pr1 = payment_requests[0]  # For provider 201, child 101
        assert pr1.google_sheets_provider_id == "201"
        assert pr1.google_sheets_child_id == "101"
        assert pr1.care_days_count == 2
        assert pr1.amount_in_cents == (care_day_1.amount_cents + care_day_2.amount_cents)
        assert set(pr1.care_day_ids) == {care_day_1.id, care_day_2.id}

        pr2 = payment_requests[1]  # For provider 202, child 101
        assert pr2.google_sheets_provider_id == "202"
        assert pr2.google_sheets_child_id == "101"
        assert pr2.care_days_count == 1
        assert pr2.amount_in_cents == care_day_3.amount_cents
        assert set(pr2.care_day_ids) == {care_day_3.id}

        # Verify care days were marked as processed
        processed_care_day_1 = db.session.get(AllocatedCareDay, care_day_1.id)
        processed_care_day_2 = db.session.get(AllocatedCareDay, care_day_2.id)
        processed_care_day_3 = db.session.get(AllocatedCareDay, care_day_3.id)
        already_processed_care_day_4 = db.session.get(AllocatedCareDay, care_day_4.id)
        not_yet_locked_care_day_5 = db.session.get(AllocatedCareDay, care_day_5.id)

        assert processed_care_day_1.payment_distribution_requested is True
        assert processed_care_day_2.payment_distribution_requested is True
        assert processed_care_day_3.payment_distribution_requested is True
        assert already_processed_care_day_4.payment_distribution_requested is True
        assert not_yet_locked_care_day_5.payment_distribution_requested is False

    # Verify that the email sending function was called
    assert mock_send_email.call_count == 2
    mock_send_email.assert_any_call(
        provider_name="Test Provider",
        google_sheets_provider_id="201",
        child_first_name="Test",
        child_last_name="Child",
        google_sheets_child_id="101",
        amount_in_cents=care_day_1.amount_cents + care_day_2.amount_cents,
        care_days=[care_day_1, care_day_2],
    )
    mock_send_email.assert_any_call(
        provider_name="Another Provider",
        google_sheets_provider_id="202",
        child_first_name="Test",
        child_last_name="Child",
        google_sheets_child_id="101",
        amount_in_cents=care_day_3.amount_cents,
        care_days=[care_day_3],
    )
