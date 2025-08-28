from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation
from app.sheets.helpers import KeyMap
from app.sheets.mappings import ChildColumnNames


@pytest.fixture(autouse=True)
def mock_google_sheets(mocker, app):
    mocker.patch("app.sheets.integration.SheetsManager.get_sheet_data", return_value=[])
    mocker.patch(
        "app.models.month_allocation.get_child",
        return_value=KeyMap(
            {
                ChildColumnNames.MONTHLY_ALLOCATION.key: "1000",
                ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "500",
                ChildColumnNames.ID.key: "1",
            }
        ),
    )
    mocker.patch(
        "app.models.month_allocation.get_children",
        return_value=[
            KeyMap(
                {
                    ChildColumnNames.MONTHLY_ALLOCATION.key: "1000",
                    ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "500",
                    ChildColumnNames.ID.key: "1",
                }
            )
        ],
    )
    # Mock the app.google_sheets_service directly on the app instance
    app.google_sheets_service = mocker.Mock()
    # Mock app.config.get to ensure GOOGLE_APPLICATION_CREDENTIALS is seen as present
    mocker.patch.object(
        app.config,
        "get",
        side_effect=lambda key, default=None: (
            "test_credentials" if key == "GOOGLE_APPLICATION_CREDENTIALS" else default
        ),
    )


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=1000000,
            google_sheets_child_id=1,
        )
        db.session.add(allocation)
        db.session.commit()

        # Care day: new (never submitted)
        care_day_new = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=7),  # Set date to a week in the future
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            last_submitted_at=None,
        )
        db.session.add(care_day_new)

        # Care day: submitted (updated_at < last_submitted_at)
        care_day_submitted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=1),  # Set date to tomorrow
            locked_date=datetime.now() + timedelta(days=20),
            type="Half Day",
            amount_cents=4000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=5),  # Submitted 5 days ago
        )
        care_day_submitted.updated_at = care_day_submitted.last_submitted_at - timedelta(
            days=1
        )  # Ensure updated_at is before last_submitted_at
        db.session.add(care_day_submitted)

        # Care day: needs resubmission (updated_at > last_submitted_at)
        care_day_needs_resubmission = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=2),  # Set date to two days from now
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=10),  # Submitted 10 days ago
        )
        care_day_needs_resubmission.updated_at = datetime.now(timezone.utc)  # Updated recently
        db.session.add(care_day_needs_resubmission)

        # Care day: locked (date is in the past, beyond locked_date)
        locked_date_past = datetime.now() - timedelta(days=7)  # A week ago
        care_day_locked = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=locked_date_past.date(),  # Ensure it's locked
            locked_date=locked_date_past,
            type="Full Day",
            amount_cents=6000,
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=10),  # Submitted 10 days ago
        )
        # Manually set created_at and updated_at to be before last_submitted_at for testing is_locked
        care_day_locked.created_at = locked_date_past - timedelta(days=11)
        care_day_locked.updated_at = locked_date_past - timedelta(days=11)
        db.session.add(care_day_locked)

        # Care day: soft deleted
        care_day_deleted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=3),  # Set date to three days from now
            locked_date=datetime.now() + timedelta(days=20),
            type="Full Day",
            amount_cents=6000,
            deleted_at=datetime.now(timezone.utc),
            last_submitted_at=datetime.now(timezone.utc) - timedelta(days=1),  # Submitted yesterday
        )
        db.session.add(care_day_deleted)

        db.session.commit()
        yield allocation, care_day_new, care_day_submitted, care_day_needs_resubmission, care_day_locked, care_day_deleted


# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"data": {"types": ["family"], "family_id": 1}}
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)


# --- GET /child/{child_id}/allocation/{month}/{year} ---
def test_get_month_allocation_success(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.get(
        f"/child/{allocation.google_sheets_child_id}/allocation/{allocation.date.month}/{allocation.date.year}?provider_id=1"
    )
    assert response.status_code == 200
    assert response.json["allocation_cents"] == 1000000
    assert len(response.json["care_days"]) == 5  # All care days for provider 1

    # Check submission statuses
    care_day_statuses = {d["id"]: d["status"] for d in response.json["care_days"]}
    assert care_day_statuses[1] == "new"
    assert care_day_statuses[2] == "submitted"
    assert care_day_statuses[3] == "needs_resubmission"
    assert care_day_statuses[4] == "submitted"
    assert care_day_statuses[5] == "delete_not_submitted"


def test_get_month_allocation_invalid_date(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.get(
        f"/child/{allocation.google_sheets_child_id}/allocation/13/2024?provider_id=1"
    )  # Invalid month
    assert response.status_code == 400
    assert "month must be in 1..12" in response.json["error"]


def test_get_month_allocation_allocation_not_found(client, seed_db, mocker):
    _, _, _, _, _, _ = seed_db
    # Mock get_children to return a list containing the mocked child data
    mock_child_data = KeyMap(
        {
            ChildColumnNames.MONTHLY_ALLOCATION.key: "5000",
            ChildColumnNames.ID.key: 999,
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION.key: "5000",
        },
    )
    mocker.patch("app.models.month_allocation.get_children", return_value=[mock_child_data])

    # Mock get_child to return the specific child data (it will be called by get_or_create_for_month)
    mocker.patch("app.models.month_allocation.get_child", return_value=mock_child_data)

    response = client.get(
        f"/child/999/allocation/{date.today().month}/{date.today().year}?provider_id=1"
    )  # Non-existent child
    assert response.status_code == 200  # Allocation will be created with default values
    assert response.json["allocation_cents"] == 500000  # 5000 dollars * 100 cents/dollar


# --- POST /child/{child_id}/provider/{provider_id}/allocation/{month}/{year}/submit ---
def test_submit_care_days_success(client, seed_db, mock_send_submission_notification, mocker):
    (
        allocation,
        care_day_new,
        _,
        care_day_needs_resubmission,
        _,
        care_day_deleted,
    ) = seed_db

    # Mock the child, provider and family data with payment enabled
    from app.sheets.mappings import (
        ChildColumnNames,
        FamilyColumnNames,
        ProviderColumnNames,
    )

    mock_child_data = {
        ChildColumnNames.ID: allocation.google_sheets_child_id,
        ChildColumnNames.FAMILY_ID: "test_family_id",
        ChildColumnNames.FIRST_NAME: "Test",
        ChildColumnNames.LAST_NAME: "Child",
    }

    mock_provider_data = {
        ProviderColumnNames.ID: care_day_new.provider_google_sheets_id,
        ProviderColumnNames.NAME: "Test Provider",
        ProviderColumnNames.PAYMENT_ENABLED: True,
    }

    mock_family_data = {
        FamilyColumnNames.ID: "test_family_id",
        FamilyColumnNames.FIRST_NAME: "Test",
        FamilyColumnNames.LAST_NAME: "Family",
        FamilyColumnNames.PAYMENT_ENABLED: True,
    }

    mocker.patch("app.routes.child.get_children", return_value=[mock_child_data])
    mocker.patch("app.routes.child.get_child", return_value=mock_child_data)
    mocker.patch("app.routes.child.get_providers", return_value=[mock_provider_data])
    mocker.patch("app.routes.child.get_provider", return_value=mock_provider_data)
    mocker.patch("app.routes.child.get_families", return_value=[mock_family_data])
    mocker.patch("app.routes.child.get_family", return_value=mock_family_data)

    response = client.post(
        f"/child/{allocation.google_sheets_child_id}/provider/{care_day_new.provider_google_sheets_id}/allocation/{allocation.date.month}/{allocation.date.year}/submit"
    )
    assert response.status_code == 200
    assert response.json["message"] == "Submission successful"

    # Verify new, modified, and removed days are in the response
    assert len(response.json["new_days"]) == 1  # care_day_new
    assert response.json["new_days"][0]["id"] == care_day_new.id
    assert len(response.json["modified_days"]) == 1  # care_day_needs_resubmission
    assert response.json["modified_days"][0]["id"] == care_day_needs_resubmission.id
    assert len(response.json["removed_days"]) == 1  # care_day_deleted
    assert response.json["removed_days"][0]["id"] == care_day_deleted.id

    # Verify send_submission_notification was called
    mock_send_submission_notification.assert_called_once()
    call_kwargs = mock_send_submission_notification.call_args.kwargs

    assert call_kwargs["provider_id"] == care_day_new.provider_google_sheets_id
    assert call_kwargs["child_id"] == allocation.google_sheets_child_id

    # Extract IDs from the actual call arguments
    actual_new_day_ids = [d.id for d in call_kwargs["new_days"]]
    actual_modified_day_ids = [d.id for d in call_kwargs["modified_days"]]
    actual_removed_day_ids = [d.id for d in call_kwargs["removed_days"]]

    assert actual_new_day_ids == [care_day_new.id]
    assert actual_modified_day_ids == [care_day_needs_resubmission.id]
    assert actual_removed_day_ids == [care_day_deleted.id]

    # Verify last_submitted_at is updated for submitted days
    with client.application.app_context():
        updated_new_day = db.session.get(AllocatedCareDay, care_day_new.id)
        updated_needs_resubmission_day = db.session.get(AllocatedCareDay, care_day_needs_resubmission.id)
        assert updated_new_day.last_submitted_at is not None
        assert updated_needs_resubmission_day.last_submitted_at is not None


def test_submit_care_days_no_care_days(client, seed_db, mock_send_submission_notification, mocker):

    # Create a new allocation with no care days
    new_allocation_child_id = "2"
    new_allocation_month = date.today().month
    new_allocation_year = date.today().year

    with client.application.app_context():
        new_allocation = MonthAllocation(
            date=date(new_allocation_year, new_allocation_month, 1),
            allocation_cents=50000,
            google_sheets_child_id=new_allocation_child_id,
        )
        db.session.add(new_allocation)
        db.session.commit()

    # Mock the child, provider and family data with payment enabled
    from app.sheets.mappings import (
        ChildColumnNames,
        FamilyColumnNames,
        ProviderColumnNames,
    )

    mock_child_data = {
        ChildColumnNames.ID: new_allocation_child_id,
        ChildColumnNames.FAMILY_ID: "test_family_id",
        ChildColumnNames.FIRST_NAME: "Test",
        ChildColumnNames.LAST_NAME: "Child",
    }

    mock_provider_data = {
        ProviderColumnNames.ID: "1",
        ProviderColumnNames.NAME: "Test Provider",
        ProviderColumnNames.PAYMENT_ENABLED: True,
    }

    mock_family_data = {
        FamilyColumnNames.ID: "test_family_id",
        FamilyColumnNames.FIRST_NAME: "Test",
        FamilyColumnNames.LAST_NAME: "Family",
        FamilyColumnNames.PAYMENT_ENABLED: True,
    }

    mocker.patch("app.routes.child.get_children", return_value=[mock_child_data])
    mocker.patch("app.routes.child.get_child", return_value=mock_child_data)
    mocker.patch("app.routes.child.get_providers", return_value=[mock_provider_data])
    mocker.patch("app.routes.child.get_provider", return_value=mock_provider_data)
    mocker.patch("app.routes.child.get_families", return_value=[mock_family_data])
    mocker.patch("app.routes.child.get_family", return_value=mock_family_data)

    response = client.post(
        f"/child/{new_allocation_child_id}/provider/1/allocation/{new_allocation_month}/{new_allocation_year}/submit"
    )
    assert response.status_code == 200
    assert response.json["message"] == "Submission successful"
    assert len(response.json["new_days"]) == 0
    assert len(response.json["modified_days"]) == 0
    assert len(response.json["removed_days"]) == 0
    mock_send_submission_notification.assert_called_once_with(
        provider_id="1",
        child_id=new_allocation_child_id,
        new_days=[],
        modified_days=[],
        removed_days=[],
    )


def test_submit_care_days_allocation_not_found(client, seed_db, mock_send_submission_notification):
    _, _, _, _, _, _ = seed_db

    response = client.post("/child/999/provider/1/allocation/1/2024/submit")  # Non-existent child
    assert response.status_code == 404
    assert "Allocation not found" in response.json["error"]
    mock_send_submission_notification.assert_not_called()


def test_submit_care_days_over_allocation_fails(client, seed_db, mock_send_submission_notification):
    allocation, _, _, _, _, _ = seed_db
    allocation.allocation_cents = 0
    db.session.commit()

    response = client.post(
        f"/child/{allocation.google_sheets_child_id}/provider/1/allocation/{allocation.date.month}/{allocation.date.year}/submit"
    )
    assert response.status_code == 400
    assert "Cannot submit: allocation exceeded" in response.json["error"]
    mock_send_submission_notification.assert_not_called()


def test_get_month_allocation_past_month_creation_fails(client):
    # Attempt to get an allocation for a past month (e.g., January of the current year)
    past_month = date.today().replace(month=1, day=1)
    response = client.get(f"/child/1/allocation/{past_month.month}/{past_month.year}?provider_id=1")
    assert response.status_code == 400
    assert "Cannot create allocation for a past month." in response.json["error"]


def test_get_month_allocation_future_month_creation_fails(client):
    # Attempt to get an allocation for a future month that is too far in advance
    future_month = date.today().replace(day=1) + timedelta(days=65)
    response = client.get(f"/child/1/allocation/{future_month.month}/{future_month.year}?provider_id=1")
    assert response.status_code == 400
    assert "Cannot create allocation for a month more than one month in the future." in response.json["error"]


def test_month_allocation_locked_until_date(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    # Calculate expected locked_until_date based on current date
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    current_monday_eod = datetime.combine(current_monday, time(23, 59, 59))

    if datetime.now() > current_monday_eod:
        expected_locked_until_date = current_monday + timedelta(days=6)  # Sunday of current week
    else:
        expected_locked_until_date = current_monday - timedelta(days=1)  # Sunday of previous week

    with client.application.app_context():
        # Refresh allocation from DB to ensure property is calculated correctly
        db.session.expire_all()
        updated_allocation = db.session.get(MonthAllocation, allocation.id)
        assert updated_allocation.locked_until_date == expected_locked_until_date
