
import pytest
from datetime import date, datetime, timedelta
from app.models import AllocatedCareDay, MonthAllocation, PaymentRate
from app.enums.care_day_type import CareDayType
from app.extensions import db
from decimal import Decimal


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a PaymentRate for testing
        payment_rate = PaymentRate(
            google_sheets_provider_id=1,
            google_sheets_child_id=1,
            full_day_rate_cents=60000,
            half_day_rate_cents=40000,
        )
        payment_rate_2 = PaymentRate(
            google_sheets_provider_id=2,
            google_sheets_child_id=1,
            full_day_rate_cents=60000,
            half_day_rate_cents=40000,
        )
        db.session.add(payment_rate)
        db.session.add(payment_rate_2)

        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=1000000,
            google_sheets_child_id=1,
        )
        db.session.add(allocation)
        db.session.commit()

        # Create a care day that is new (never submitted)
        care_day_new = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=7), # Set date to a week in the future
            locked_date=datetime.now() + timedelta(days=20),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None
        )
        db.session.add(care_day_new)
        db.session.commit()

        yield allocation, care_day_new, payment_rate, payment_rate_2

# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {'data': {'types': ['family'], 'family_id': 1}}
    mocker.patch('app.auth.decorators._authenticate_request', return_value=mock_request_state)

def test_create_care_day_duplicate_date_different_provider(client, seed_db):
    allocation, care_day_new, _, payment_rate = seed_db
    # Care day with ID 1 already exists for provider 1
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 2, # Different provider
            "date": care_day_new.date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 201
    assert response.json["amount_cents"] == payment_rate.full_day_rate_cents

def test_create_care_day_duplicate_date_same_provider(client, seed_db):
    allocation, care_day_new, _, _ = seed_db
    # Care day with ID 1 already exists for provider 1
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1, # Same provider
            "date": care_day_new.date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Care day already exists for this date" in response.json["error"]

def test_get_month_allocation_no_provider_id(client, seed_db):
    allocation, _, _, _ = seed_db
    response = client.get(
        f"/child/{allocation.google_sheets_child_id}/allocation/{allocation.date.month}/{allocation.date.year}"
    )
    assert response.status_code == 200
    assert len(response.json["care_days"]) == 1
