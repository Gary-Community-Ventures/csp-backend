from datetime import date, datetime, timedelta, timezone

import pytest

from app.enums.care_day_type import CareDayType
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation, PaymentRate


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a PaymentRate for testing
        payment_rate = PaymentRate(
            google_sheets_provider_id="1",
            google_sheets_child_id="1",
            full_day_rate_cents=60000,
            half_day_rate_cents=40000,
        )
        db.session.add(payment_rate)

        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=1000000,
            google_sheets_child_id="1",
        )
        db.session.add(allocation)
        db.session.commit()

        # Create a care day that is new (never submitted)
        care_day_new = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id="1",
            date=date.today() + timedelta(days=7),  # Set date to a week in the future
            locked_date=datetime.now(timezone.utc) + timedelta(days=20),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None,
        )
        db.session.add(care_day_new)
        db.session.commit()

        # Create a care day that can be updated/deleted
        care_day_updatable = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id="1",
            date=date.today() + timedelta(days=1),  # Set date to tomorrow
            locked_date=datetime.now(timezone.utc) + timedelta(days=8),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None,  # Never submitted
        )
        db.session.add(care_day_updatable)
        db.session.commit()

        # Create a locked care day
        locked_date = datetime.now(timezone.utc) - timedelta(days=7)  # A week ago
        care_day_locked = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id="1",
            locked_date=locked_date,
            date=locked_date.date(),
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=datetime.now(timezone.utc),  # Submitted
        )
        # Manually set created_at and updated_at to be before locked_date for testing is_locked
        care_day_locked.created_at = locked_date - timedelta(days=1)
        care_day_locked.updated_at = locked_date - timedelta(days=1)
        db.session.add(care_day_locked)
        db.session.commit()

        # Create a soft-deleted care day
        care_day_soft_deleted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id="1",
            date=date.today() + timedelta(days=2),  # Set date to two days from now
            locked_date=datetime.now(timezone.utc) + timedelta(days=10),  # Set locked_date to future
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            deleted_at=datetime.now(timezone.utc),
        )
        db.session.add(care_day_soft_deleted)
        db.session.commit()

        yield allocation, care_day_new, care_day_updatable, care_day_locked, care_day_soft_deleted, payment_rate


# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"data": {"types": ["family"], "family_id": 1}}
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)


# --- POST /care-days ---
def test_create_care_day_success(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": (date.today() + timedelta(days=10)).isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 201
    assert response.json["day_count"] == 1.0
    assert response.json["amount_cents"] == payment_rate.full_day_rate_cents
    assert AllocatedCareDay.query.filter_by(date=date.today() + timedelta(days=10)).first() is not None


def test_create_care_day_missing_fields(client, seed_db):
    _, _, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "provider_id": "1",
            "date": "2024-01-17",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Missing required fields" in response.json["error"]


def test_create_care_day_invalid_date_format(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": "invalid-date",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Invalid date format" in response.json["error"]


def test_create_care_day_allocation_not_found(client, seed_db):
    _, _, _, _, _, _ = seed_db
    response = client.post(
        "/care-days",
        json={
            "allocation_id": 999,  # Non-existent ID
            "provider_id": "1",
            "date": "2024-01-17",
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 404
    assert "MonthAllocation not found" in response.json["error"]


def test_create_care_day_exceeds_allocation(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db
    # Create many care days to exceed allocation
    with client.application.app_context():
        # Fill up allocation
        for i in range(1, 20):  # 10 full days
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_google_sheets_id="1",
                locked_date=datetime.now(timezone.utc) + timedelta(days=10),
                date=date.today() + timedelta(days=i + 10),
                type=CareDayType.FULL_DAY,
                amount_cents=payment_rate.full_day_rate_cents,
            )
            db.session.add(care_day)
        db.session.commit()

    allocation = db.session.get(MonthAllocation, allocation.id)

    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": (date.today() + timedelta(days=30)).isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Adding this care day would exceed monthly allocation" in response.json["error"]


def test_create_care_day_restore_soft_deleted(client, seed_db):
    allocation, _, _, _, care_day_soft_deleted, _ = seed_db
    # Attempt to create a care day on the same date as the soft-deleted one
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": care_day_soft_deleted.provider_google_sheets_id,
            "date": care_day_soft_deleted.date.isoformat(),
            "type": "Full Day",
        },
    )
    assert response.status_code == 201
    assert response.json["id"] == care_day_soft_deleted.id
    assert response.json["is_deleted"] is False

    with client.application.app_context():
        restored_day = db.session.get(AllocatedCareDay, care_day_soft_deleted.id)
        assert restored_day.is_deleted is False
        assert restored_day.type == CareDayType.FULL_DAY


def test_create_care_day_past_date_fails(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    past_date = date.today() - timedelta(days=1)
    response = client.post(
        "/care-days",
        json={"allocation_id": allocation.id, "provider_id": "1", "date": past_date.isoformat(), "type": "Full Day"},
    )
    assert response.status_code == 400
    assert "Cannot create a care day in the past." in response.json["error"]


# --- PUT /care-days/<care_day_id> ---
def test_update_care_day_success(client, seed_db):
    _, _, care_day_updatable, _, _, _ = seed_db
    response = client.put(f"/care-days/{care_day_updatable.id}", json={"type": CareDayType.HALF_DAY.value})
    assert response.status_code == 200
    assert response.json["type"] == CareDayType.HALF_DAY.value
    with client.application.app_context():
        updated_day = db.session.get(AllocatedCareDay, care_day_updatable.id)
        assert updated_day.type == CareDayType.HALF_DAY
        # Check if needs_resubmission is true (because last_submitted_at is None)
        assert updated_day.needs_resubmission is True


def test_update_care_day_not_found(client, seed_db):
    _, _, _, _, _, _ = seed_db
    response = client.put("/care-days/999", json={"type": CareDayType.HALF_DAY.value})
    assert response.status_code == 404
    assert "Care day not found" in response.json["error"]


def test_update_care_day_locked(client, seed_db):
    _, _, _, care_day_locked, _, _ = seed_db
    # Care day with ID 2 is locked
    response = client.put(f"/care-days/{care_day_locked.id}", json={"type": CareDayType.HALF_DAY.value})
    assert response.status_code == 403
    assert "Cannot modify a locked care day" in response.json["error"]


def test_update_care_day_missing_type(client, seed_db):
    _, _, care_day_updatable, _, _, _ = seed_db
    response = client.put(f"/care-days/{care_day_updatable.id}", json={})
    assert response.status_code == 400
    assert "Missing type field" in response.json["error"]


def test_update_care_day_over_allocation_soft_deletes(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db
    # Set allocation to be less than a full day
    allocation.allocation_cents = payment_rate.half_day_rate_cents
    db.session.commit()

    # Create a half day care day
    care_day = AllocatedCareDay(
        care_month_allocation_id=allocation.id,
        provider_google_sheets_id="1",
        date=date.today() + timedelta(days=3),
        locked_date=datetime.now(timezone.utc) + timedelta(days=10),
        type=CareDayType.HALF_DAY,
        amount_cents=payment_rate.half_day_rate_cents,
    )
    db.session.add(care_day)
    db.session.commit()

    # Update the care day to a full day, which should exceed the allocation
    response = client.put(f"/care-days/{care_day.id}", json={"type": CareDayType.FULL_DAY.value})
    assert response.status_code == 200
    assert response.json["is_deleted"] is True

    with client.application.app_context():
        updated_day = db.session.get(AllocatedCareDay, care_day.id)
        assert updated_day.is_deleted is True


# --- DELETE /care-days/<care_day_id> ---
def test_delete_care_day_success(client, seed_db):
    _, _, care_day_updatable, _, _, _ = seed_db
    response = client.delete(f"/care-days/{care_day_updatable.id}")
    assert response.status_code == 204
    with client.application.app_context():
        deleted_day = db.session.get(AllocatedCareDay, care_day_updatable.id)
        assert deleted_day.deleted_at is not None


def test_delete_care_day_not_found(client, seed_db):
    _, _, _, _, _, _ = seed_db
    response = client.delete("/care-days/999")
    assert response.status_code == 404
    assert "Care day not found" in response.json["error"]


def test_delete_care_day_locked(client, seed_db):
    _, _, _, care_day_locked, _, _ = seed_db
    # Care day with ID 2 is locked
    response = client.delete(f"/care-days/{care_day_locked.id}")
    assert response.status_code == 403
    assert "Cannot delete a locked care day" in response.json["error"]


def test_update_soft_deleted_care_day_restores_and_updates(client, seed_db):
    _, _, _, _, care_day_soft_deleted, payment_rate = seed_db

    # Ensure the care_day_soft_deleted is indeed soft-deleted initially
    with client.application.app_context():
        initial_deleted_day = db.session.get(AllocatedCareDay, care_day_soft_deleted.id)
        assert initial_deleted_day.is_deleted is True

    # Attempt to update the soft-deleted care day
    response = client.put(
        f"/care-days/{care_day_soft_deleted.id}",
        json={"type": CareDayType.HALF_DAY.value},  # Change type to trigger recalculation and last_submitted_at reset
    )
    assert response.status_code == 200
    assert response.json["id"] == care_day_soft_deleted.id
    assert response.json["is_deleted"] is False
    assert response.json["type"] == CareDayType.HALF_DAY.value
    assert response.json["last_submitted_at"] is None

    with client.application.app_context():
        restored_and_updated_day = db.session.get(AllocatedCareDay, care_day_soft_deleted.id)
        assert restored_and_updated_day.is_deleted is False
        assert restored_and_updated_day.type == CareDayType.HALF_DAY
        assert restored_and_updated_day.last_submitted_at is None
        assert restored_and_updated_day.amount_cents == payment_rate.half_day_rate_cents
