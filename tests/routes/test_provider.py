import pytest
from datetime import date, datetime, timedelta
from app.models import AllocatedCareDay, MonthAllocation
from app.extensions import db
from decimal import Decimal


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create MonthAllocations for different children
        allocation1 = MonthAllocation(
            date=date(2024, 1, 1), allocation_cents=1000000, google_sheets_child_id=1
        )
        allocation2 = MonthAllocation(
            date=date(2024, 2, 1), allocation_cents=50000, google_sheets_child_id=2
        )
        db.session.add(allocation1)
        db.session.add(allocation2)
        db.session.commit()

        # Care days for provider 1, child 1
        care_day1_1 = AllocatedCareDay(
            care_month_allocation_id=allocation1.id,
            date=date(2024, 1, 15),
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            provider_google_sheets_id=1,
        )
        care_day1_2 = AllocatedCareDay(
            care_month_allocation_id=allocation1.id,
            date=date(2024, 1, 20),
            locked_date=datetime.now() + timedelta(days=20),
            type="Half Day",
            amount_cents=4000,
            provider_google_sheets_id=1,
        )
        db.session.add(care_day1_1)
        db.session.add(care_day1_2)

        # Care days for provider 1, child 2
        care_day2_1 = AllocatedCareDay(
            care_month_allocation_id=allocation2.id,
            date=date(2024, 2, 10),
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            provider_google_sheets_id=1,
        )
        db.session.add(care_day2_1)

        # Care days for provider 2, child 1 (should not be returned for provider 1 queries)
        care_day_other_provider = AllocatedCareDay(
            care_month_allocation_id=allocation1.id,
            date=date(2024, 1, 25),
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            provider_google_sheets_id=2,
        )
        db.session.add(care_day_other_provider)

        db.session.commit()
        yield allocation1, allocation2, care_day1_1, care_day1_2, care_day2_1, care_day_other_provider


# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"data": {"types": ["provider"], "provider_id": 1}}
    mocker.patch(
        "app.auth.decorators._authenticate_request", return_value=mock_request_state
    )


# --- GET /provider/{provider_id}/allocated_care_days ---
def test_get_allocated_care_days_success_no_filters(client, seed_db):
    allocation1, allocation2, care_day1_1, care_day1_2, care_day2_1, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days"
    )
    assert response.status_code == 200
    assert (
        str(allocation1.google_sheets_child_id) in response.json
    )  # Grouped by child_id 1
    assert (
        str(allocation2.google_sheets_child_id) in response.json
    )  # Grouped by child_id 2
    assert (
        len(response.json[str(allocation1.google_sheets_child_id)]) == 2
    )  # Two care days for child 1
    assert (
        len(response.json[str(allocation2.google_sheets_child_id)]) == 1
    )  # One care day for child 2
    assert (
        response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_1.id
        or response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_2.id
    )
    assert (
        response.json[str(allocation2.google_sheets_child_id)][0]["id"]
        == care_day2_1.id
    )


def test_get_allocated_care_days_filter_by_child_id(client, seed_db):
    allocation1, _, care_day1_1, _, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?childId={allocation1.google_sheets_child_id}"
    )
    assert response.status_code == 200
    assert str(allocation1.google_sheets_child_id) in response.json
    assert str(allocation1.google_sheets_child_id) + "x" not in response.json
    assert len(response.json[str(allocation1.google_sheets_child_id)]) == 2


def test_get_allocated_care_days_filter_by_start_date(client, seed_db):
    allocation1, allocation2, care_day1_1, care_day1_2, care_day2_1, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?startDate=2024-01-16"
    )
    assert response.status_code == 200
    assert str(allocation1.google_sheets_child_id) in response.json
    assert str(allocation2.google_sheets_child_id) in response.json
    assert (
        len(response.json[str(allocation1.google_sheets_child_id)]) == 1
    )  # Only care_day1_2 (2024-01-20) remains for child 1
    assert (
        response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_2.id
    )
    assert (
        len(response.json[str(allocation2.google_sheets_child_id)]) == 1
    )  # care_day2_1 (2024-02-10) remains for child 2


def test_get_allocated_care_days_filter_by_end_date(client, seed_db):
    allocation1, allocation2, care_day1_1, care_day1_2, care_day2_1, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?endDate=2024-01-18"
    )
    assert response.status_code == 200
    assert str(allocation1.google_sheets_child_id) in response.json
    assert (
        str(allocation2.google_sheets_child_id) not in response.json
    )  # Child 2 care day is after end date
    assert (
        len(response.json[str(allocation1.google_sheets_child_id)]) == 1
    )  # Only care_day1_1 (2024-01-15) remains for child 1
    assert (
        response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_1.id
    )


def test_get_allocated_care_days_filter_by_start_and_end_date(client, seed_db):
    allocation1, _, _, care_day1_2, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_2.provider_google_sheets_id}/allocated_care_days?startDate=2024-01-16&endDate=2024-01-22"
    )
    assert response.status_code == 200
    assert str(allocation1.google_sheets_child_id) in response.json
    assert str(int(allocation1.google_sheets_child_id) + 1) not in response.json
    assert (
        len(response.json[str(allocation1.google_sheets_child_id)]) == 1
    )  # Only care_day1_2 (2024-01-20) remains
    assert (
        response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_2.id
    )


def test_get_allocated_care_days_filter_all_params(client, seed_db):
    allocation1, _, _, care_day1_2, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_2.provider_google_sheets_id}/allocated_care_days?childId={allocation1.google_sheets_child_id}&startDate=2024-01-16&endDate=2024-01-22"
    )
    assert response.status_code == 200
    assert str(allocation1.google_sheets_child_id) in response.json
    assert str(allocation1.google_sheets_child_id) + "X" not in response.json
    assert (
        len(response.json[str(allocation1.google_sheets_child_id)]) == 1
    )  # Only care_day1_2 (2024-01-20) remains
    assert (
        response.json[str(allocation1.google_sheets_child_id)][0]["id"]
        == care_day1_2.id
    )


def test_get_allocated_care_days_no_results(client, seed_db):
    allocation1, _, care_day1_1, _, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?startDate=2025-01-01"
    )  # Future date
    assert response.status_code == 200
    assert len(response.json) == 0


def test_get_allocated_care_days_invalid_start_date(client, seed_db):
    allocation1, _, care_day1_1, _, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?startDate=invalid-date"
    )
    assert response.status_code == 400
    assert "Invalid startDate format" in response.json["error"]


def test_get_allocated_care_days_invalid_end_date(client, seed_db):
    allocation1, _, care_day1_1, _, _, _ = seed_db
    response = client.get(
        f"/provider/{care_day1_1.provider_google_sheets_id}/allocated_care_days?endDate=invalid-date"
    )
    assert response.status_code == 400
    assert "Invalid endDate format" in response.json["error"]
