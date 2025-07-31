import pytest
from datetime import date, datetime, timedelta
from app.models import AllocatedCareDay, MonthAllocation
from app.models.utils import get_care_day_cost
from app.extensions import db
from decimal import Decimal

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
        db.session.add(payment_rate)

        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date(2024, 1, 1),
            allocation_cents=1000000,
            google_sheets_child_id=1,
        )
        db.session.add(allocation)
        db.session.commit()

        # Create a care day that can be updated/deleted
        care_day_updatable = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=datetime.now(),
            locked_date=datetime.now() + timedelta(days=8),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None,  # Never submitted
        )
        db.session.add(care_day_updatable)
        db.session.commit()

        # Create a locked care day
        locked_date = datetime.now() - timedelta(days=7)  # A week ago
        care_day_locked = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            locked_date=locked_date,
            date=locked_date.date(),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=datetime.utcnow(),  # Submitted
        )
        # Manually set created_at and updated_at to be before locked_date for testing is_locked
        care_day_locked.created_at = locked_date - timedelta(days=1)
        care_day_locked.updated_at = locked_date - timedelta(days=1)
        db.session.add(care_day_locked)
        db.session.commit()

        # Create a soft-deleted care day
        care_day_soft_deleted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date(2024, 1, 16),
            locked_date=datetime.now(),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            deleted_at=datetime.utcnow(),
        )
        db.session.add(care_day_soft_deleted)
        db.session.commit()

        yield allocation, care_day_updatable, care_day_locked, care_day_soft_deleted, payment_rate

# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {'data': {'types': ['family'], 'family_id': 1}}
    mocker.patch('app.auth.decorators._authenticate_request', return_value=mock_request_state)

# --- POST /care-days ---
def test_create_care_day_success(client, seed_db):
    allocation, _, _, _, payment_rate = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1,
            "date": "2024-01-17",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 201
    assert response.json["day_count"] == 1.0
    assert response.json["amount_cents"] == payment_rate.full_day_rate_cents
    assert (
        AllocatedCareDay.query.filter_by(date=date(2024, 1, 17)).first() is not None
    )


def test_create_care_day_missing_fields(client, seed_db):
    allocation, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "provider_id": 1,
            "date": "2024-01-17",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Missing required fields" in response.json["error"]

def test_create_care_day_invalid_date_format(client, seed_db):
    allocation, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1,
            "date": "invalid-date",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Invalid date format" in response.json["error"]

def test_create_care_day_allocation_not_found(client, seed_db):
    _, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": 999,  # Non-existent ID
            "provider_id": 1,
            "date": "2024-01-17",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 404
    assert "MonthAllocation not found" in response.json["error"]

def test_create_care_day_exceeds_allocation(client, seed_db):
    allocation, _, _, _, payment_rate = seed_db
    # Create many care days to exceed allocation
    with client.application.app_context():
        # Fill up allocation
        for i in range(1, 20):  # 10 full days
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_google_sheets_id=1,
                locked_date=datetime.now(),
                date=date(2024, 2, i),
                type=CareDayType.FULL_DAY,
                amount_cents=payment_rate.full_day_rate_cents,
            )
            db.session.add(care_day)
        db.session.commit()

    allocation = MonthAllocation.query.get(allocation.id)

    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1,
            "date": "2024-02-11",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "exceed monthly allocation" in response.json["error"]

def test_create_care_day_duplicate_date(client, seed_db):
    allocation, care_day_updatable, _, _, _ = seed_db
    # Care day with ID 1 already exists for 2024-01-15
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1,
            "date": care_day_updatable.date.isoformat(),
            "type": CareDayType.HALF_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Care day already exists for this date" in response.json["error"]

def test_create_care_day_restore_soft_deleted(client, seed_db):
    allocation, _, _, care_day_soft_deleted, _ = seed_db
    # Care day with ID 3 is soft-deleted for 2024-01-16
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": 1,
            "date": care_day_soft_deleted.date.isoformat(),
            "type": CareDayType.HALF_DAY.value,
        },
    )
    assert response.status_code == 201
    assert (
        response.json["id"] == care_day_soft_deleted.id
    )  # Should restore the existing one
    assert response.json["type"] == CareDayType.HALF_DAY.value
    with client.application.app_context():
        restored_day = AllocatedCareDay.query.get(care_day_soft_deleted.id)
        assert restored_day.deleted_at is None
        assert restored_day.type == CareDayType.HALF_DAY

# --- PUT /care-days/<care_day_id> ---
def test_update_care_day_success(client, seed_db):
    _, care_day_updatable, _, _, _ = seed_db
    response = client.put(
        f"/care-days/{care_day_updatable.id}", json={"type": CareDayType.HALF_DAY.value}
    )
    assert response.status_code == 200
    assert response.json["type"] == CareDayType.HALF_DAY.value
    with client.application.app_context():
        updated_day = AllocatedCareDay.query.get(care_day_updatable.id)
        assert updated_day.type == CareDayType.HALF_DAY
        # Check if needs_resubmission is true (because last_submitted_at is None)
        assert updated_day.needs_resubmission is True

def test_update_care_day_not_found(client, seed_db):
    _, _, _, _, _ = seed_db
    response = client.put("/care-days/999", json={"type": CareDayType.HALF_DAY.value})
    assert response.status_code == 404
    assert "Care day not found" in response.json["error"]

def test_update_care_day_locked(client, seed_db):
    _, _, care_day_locked, _, _ = seed_db
    # Care day with ID 2 is locked
    response = client.put(f"/care-days/{care_day_locked.id}", json={"type": CareDayType.HALF_DAY.value})
    assert response.status_code == 403
    assert "Cannot modify a locked care day" in response.json["error"]

def test_update_care_day_missing_type(client, seed_db):
    _, care_day_updatable, _, _, _ = seed_db
    response = client.put(f"/care-days/{care_day_updatable.id}", json={})
    assert response.status_code == 400
    assert "Missing type field" in response.json["error"]

# --- DELETE /care-days/<care_day_id> ---
def test_delete_care_day_success(client, seed_db):
    _, care_day_updatable, _, _, _ = seed_db
    response = client.delete(f"/care-days/{care_day_updatable.id}")
    assert response.status_code == 204
    with client.application.app_context():
        deleted_day = AllocatedCareDay.query.get(care_day_updatable.id)
        assert deleted_day.deleted_at is not None

def test_delete_care_day_not_found(client, seed_db):
    _, _, _, _, _ = seed_db
    response = client.delete("/care-days/999")
    assert response.status_code == 404
    assert "Care day not found" in response.json["error"]

def test_delete_care_day_locked(client, seed_db):
    _, _, care_day_locked, _, _ = seed_db
    # Care day with ID 2 is locked
    response = client.delete(f"/care-days/{care_day_locked.id}")
    assert response.status_code == 403
    assert "Cannot delete a locked care day" in response.json["error"]
