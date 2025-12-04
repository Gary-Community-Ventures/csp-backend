import zoneinfo
from datetime import date, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from app.constants import BUSINESS_TIMEZONE
from app.utils.date_utils import get_relative_week

# Freeze time for all tests in this module to ensure predictable behavior
TEST_FROZEN_TIME = "2025-01-15 10:00:00"  # Wednesday, Jan 15, 2025 at 10 AM
from app.enums.care_day_type import CareDayType
from app.extensions import db
from app.models import (
    AllocatedCareDay,
    MonthAllocation,
    PaymentRate,
)

business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a PaymentRate for testing
        payment_rate = PaymentRate(
            provider_supabase_id="1",
            child_supabase_id="1",
            full_day_rate_cents=60000,
            half_day_rate_cents=40000,
        )
        db.session.add(payment_rate)

        # Create a MonthAllocation for January 2025 (our frozen time)
        allocation = MonthAllocation(
            date=date(2025, 1, 1),  # January 1, 2025
            allocation_cents=1000000,
            child_supabase_id="1",
        )
        db.session.add(allocation)
        db.session.commit()

        # Create a care day that is new (never submitted)
        care_day_new = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="1",
            date=date(2025, 1, 20),  # Future date in January
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None,
        )
        db.session.add(care_day_new)
        db.session.commit()

        # Create a care day that can be updated/deleted
        care_day_updatable = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="1",
            date=date(2025, 1, 22),  # Future date in January
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=None,  # Never submitted
        )
        db.session.add(care_day_updatable)
        db.session.commit()

        # Create a locked care day (from a past date that would be locked)
        care_day_locked = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="1",
            date=date(2025, 1, 6),  # Early in January, would be locked
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            last_submitted_at=datetime.now(timezone.utc),  # Submitted
        )
        db.session.add(care_day_locked)
        db.session.commit()

        # Create a soft-deleted care day
        care_day_soft_deleted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="1",
            date=date(2025, 1, 25),  # Future date in January
            type=CareDayType.FULL_DAY,
            amount_cents=payment_rate.full_day_rate_cents,
            deleted_at=datetime.now(timezone.utc),
        )
        db.session.add(care_day_soft_deleted)
        db.session.commit()

        yield allocation, care_day_new, care_day_updatable, care_day_locked, care_day_soft_deleted, payment_rate


# Freeze time for all tests in this file
@pytest.fixture(autouse=True)
def freeze_test_time():
    with freeze_time(TEST_FROZEN_TIME):
        yield


# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"data": {"types": ["family"], "family_id": "1"}}
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)


# --- POST /care-days ---
def test_create_care_day_success(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db
    # Use a future date in January that won't be locked (TEST_FROZEN_TIME is Jan 15, Wed)
    care_date = date(2025, 1, 21)  # Next Tuesday - safely in future and won't be locked
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": care_date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 201
    assert response.json["day_count"] == 1.0
    assert response.json["amount_cents"] == payment_rate.full_day_rate_cents
    assert AllocatedCareDay.query.filter_by(date=care_date).first() is not None


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

    # Create enough care days to use up the entire allocation
    # Seed already has 3 care days (180000 cents), need to add more to fill allocation (1000000 cents)
    with client.application.app_context():
        allocation = db.session.get(MonthAllocation, allocation.id)
        remaining = allocation.remaining_unselected_cents
        full_day_cost = payment_rate.full_day_rate_cents  # 60000 cents

        # Add care days until we've used almost all the allocation
        # Use provider 2 to avoid conflicts with existing care days for provider 1
        day_num = 1
        provider_num = 2
        while remaining >= full_day_cost:
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_supabase_id=str(provider_num),
                date=date(2025, 1, day_num),
                type=CareDayType.FULL_DAY,
                amount_cents=full_day_cost,
            )
            db.session.add(care_day)
            db.session.commit()

            allocation = db.session.get(MonthAllocation, allocation.id)
            remaining = allocation.remaining_unselected_cents
            day_num += 1

            # Move to next provider if we run out of days
            if day_num > 31:
                day_num = 1
                provider_num += 1

            # Prevent infinite loop
            if provider_num > 100:
                break

        # Verify we've used up most of the allocation
        allocation = db.session.get(MonthAllocation, allocation.id)
        assert allocation.remaining_unselected_cents < full_day_cost

        # Add one more care day to use up ALL remaining allocation (including partial amounts)
        if allocation.remaining_unselected_cents > 0:
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_supabase_id="999",
                date=date(2025, 1, 15),  # Use a unique date
                type=CareDayType.HALF_DAY,  # Use half day to avoid exceeding
                amount_cents=allocation.remaining_unselected_cents,  # Use exact remaining amount
            )
            db.session.add(care_day)
            db.session.commit()

        # Verify allocation is now completely full
        allocation = db.session.get(MonthAllocation, allocation.id)
        assert allocation.remaining_unselected_cents == 0

    # Now try to create a care day - should fail because allocation is completely full
    care_date = date(2025, 1, 28)  # Future date in January
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": care_date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "Adding this care day would exceed monthly allocation" in response.json["error"]


def test_create_care_day_partial_payment(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db

    # Use up allocation except for a small amount (less than a full day cost)
    with client.application.app_context():
        allocation = db.session.get(MonthAllocation, allocation.id)
        full_day_cost = payment_rate.full_day_rate_cents  # 60000 cents
        partial_amount = 25000  # Leave only 25000 cents remaining

        # Add care days to leave only partial_amount remaining
        remaining = allocation.remaining_unselected_cents
        day_num = 1
        provider_num = 2

        # Add full day care days until adding one more would exceed our target
        while remaining - full_day_cost >= partial_amount:
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_supabase_id=str(provider_num),
                date=date(2025, 1, day_num),
                type=CareDayType.FULL_DAY,
                amount_cents=full_day_cost,
            )
            db.session.add(care_day)
            db.session.commit()

            allocation = db.session.get(MonthAllocation, allocation.id)
            remaining = allocation.remaining_unselected_cents
            day_num += 1

            if day_num > 31:
                day_num = 1
                provider_num += 1

            if provider_num > 100:
                break

        # Now adjust to get exactly partial_amount remaining if needed
        allocation = db.session.get(MonthAllocation, allocation.id)
        remaining = allocation.remaining_unselected_cents

        if remaining > partial_amount:
            # Add one more care day with exact amount to leave partial_amount
            amount_to_add = remaining - partial_amount
            care_day = AllocatedCareDay(
                care_month_allocation_id=allocation.id,
                provider_supabase_id=str(provider_num),
                date=date(2025, 1, day_num),
                type=CareDayType.HALF_DAY,
                amount_cents=amount_to_add,
            )
            db.session.add(care_day)
            db.session.commit()

        # Verify we have the right amount remaining
        allocation = db.session.get(MonthAllocation, allocation.id)
        assert allocation.remaining_unselected_cents == partial_amount

    # Now create a full day care day which should result in partial payment
    care_date = date(2025, 1, 28)
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": care_date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )

    # Should succeed with 201
    assert response.status_code == 201

    # Verify the care day has partial payment information
    care_day_data = response.json
    assert care_day_data["amount_cents"] == partial_amount
    assert care_day_data["amount_missing_cents"] == full_day_cost - partial_amount
    assert care_day_data["is_partial_payment"] is True

    # Verify in database
    with client.application.app_context():
        care_day = AllocatedCareDay.query.filter_by(
            date=care_date, provider_supabase_id="1", care_month_allocation_id=allocation.id
        ).first()
        assert care_day is not None
        assert care_day.amount_cents == partial_amount
        assert care_day.amount_missing_cents == full_day_cost - partial_amount
        assert care_day.is_partial_payment is True

        # Verify allocation is now fully used
        allocation = db.session.get(MonthAllocation, allocation.id)
        assert allocation.remaining_unselected_cents == 0


def test_create_care_day_wrong_month(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    # Try to create a care day in a different month - should fail
    different_month_date = date(2025, 2, 15)  # February (different from January allocation)
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": different_month_date.isoformat(),
            "type": CareDayType.FULL_DAY.value,
        },
    )
    assert response.status_code == 400
    assert "must be in the same month as the allocation" in response.json["error"]


def test_create_care_day_restore_soft_deleted(client, seed_db):
    allocation, _, _, _, care_day_soft_deleted, _ = seed_db
    # Attempt to create a care day on the same date as the soft-deleted one
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": care_day_soft_deleted.provider_supabase_id,
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
    # Use a past date in January (TEST_FROZEN_TIME is Jan 15)
    past_date = date(2025, 1, 10)  # Past date in January
    response = client.post(
        "/care-days",
        json={
            "allocation_id": allocation.id,
            "provider_id": "1",
            "date": past_date.isoformat(),
            "type": "Full Day",
        },
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
        # Check if needs_submission is true (because last_submitted_at is None)
        assert updated_day.needs_submission is True


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


def test_update_care_day_selected_over_allocation_soft_deletes(client, seed_db):
    allocation, _, _, _, _, payment_rate = seed_db
    # Set allocation to be less than a full day
    allocation.allocation_cents = payment_rate.half_day_rate_cents
    db.session.commit()

    # Create a half day care day in next week to ensure it's not locked
    next_week_date = get_relative_week(3)
    care_day = AllocatedCareDay(
        care_month_allocation_id=allocation.id,
        provider_supabase_id="1",
        date=next_week_date + timedelta(days=5),
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
