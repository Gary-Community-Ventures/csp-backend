import pytest
from datetime import date, datetime, timedelta
from app.models import AllocatedCareDay, MonthAllocation
from app.extensions import db
from decimal import Decimal

@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date(2024, 1, 1),
            allocation_dollars=1000.00,
            allocation_days=10.0,
            google_sheets_child_id=1
        )
        db.session.add(allocation)
        db.session.commit()

        # Care day: new (never submitted)
        care_day_new = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=7), # Set date to a week in the future
            type='Full Day',
            amount_dollars=60,
            day_count=Decimal("1.0"),
            last_submitted_at=None
        )
        db.session.add(care_day_new)

        # Care day: submitted (updated_at < last_submitted_at)
        care_day_submitted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=1), # Set date to tomorrow
            type='Half Day',
            amount_dollars=40,
            day_count=Decimal("0.5"),
            last_submitted_at=datetime.utcnow() - timedelta(days=5) # Submitted 5 days ago
        )
        care_day_submitted.updated_at = care_day_submitted.last_submitted_at - timedelta(days=1)
        db.session.add(care_day_submitted)

        # Care day: needs resubmission (updated_at > last_submitted_at)
        care_day_needs_resubmission = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=2), # Set date to two days from now
            type='Full Day',
            amount_dollars=60,
            day_count=Decimal("1.0"),
            last_submitted_at=datetime.utcnow() - timedelta(days=10) # Submitted 10 days ago
        )
        care_day_needs_resubmission.updated_at = datetime.utcnow() # Updated recently
        db.session.add(care_day_needs_resubmission)

        # Care day: locked (date is in the past, beyond locked_date)
        locked_date_past = datetime.now() - timedelta(days=7) # A week ago
        care_day_locked = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=locked_date_past.date() - timedelta(days=7), # Ensure it's locked
            type='Full Day',
            amount_dollars=60,
            day_count=Decimal("1.0"),
            last_submitted_at=datetime.utcnow()
        )
        db.session.add(care_day_locked)

        # Care day: soft deleted
        care_day_deleted = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=1,
            date=date.today() + timedelta(days=3), # Set date to three days from now
            type='Full Day',
            amount_dollars=60,
            day_count=Decimal("1.0"),
            deleted_at=datetime.utcnow()
        )
        db.session.add(care_day_deleted)

        db.session.commit()
        yield allocation, care_day_new, care_day_submitted, care_day_needs_resubmission, care_day_locked, care_day_deleted

# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {'data': {'types': ['family'], 'family_id': 1}}
    mocker.patch('app.auth.decorators._authenticate_request', return_value=mock_request_state)

# --- GET /api/family/{family_id}/child/{child_id}/allocation/{month}/{year} ---
def test_get_month_allocation_success(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.get(f'/api/family/1/child/{allocation.google_sheets_child_id}/allocation/{allocation.date.month}/{allocation.date.year}?provider_id=1')
    assert response.status_code == 200
    assert response.json['total_dollars'] == "1000.00"
    assert response.json['total_days'] == "10.0"
    assert len(response.json['care_days']) == 5 # All care days for provider 1

    # Check submission statuses
    care_day_statuses = {d['id']: d['status'] for d in response.json['care_days']}
    assert care_day_statuses[1] == 'new'
    assert care_day_statuses[2] == 'submitted'
    assert care_day_statuses[3] == 'needs_resubmission'
    assert care_day_statuses[4] == 'submitted'
    assert care_day_statuses[5] == 'deleted'

def test_get_month_allocation_missing_provider_id(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.get(f'/api/family/1/child/{allocation.google_sheets_child_id}/allocation/{allocation.date.month}/{allocation.date.year}')
    assert response.status_code == 400
    assert 'provider_id query parameter is required' in response.json['error']

def test_get_month_allocation_invalid_date(client, seed_db):
    allocation, _, _, _, _, _ = seed_db
    response = client.get(f'/api/family/1/child/{allocation.google_sheets_child_id}/allocation/13/2024?provider_id=1') # Invalid month
    assert response.status_code == 400
    assert 'Invalid month or year' in response.json['error']

def test_get_month_allocation_allocation_not_found(client, seed_db):
    _, _, _, _, _, _ = seed_db
    response = client.get('/api/family/1/child/999/allocation/1/2024?provider_id=1') # Non-existent child
    assert response.status_code == 200 # Allocation will be created with default values
    assert response.json['total_dollars'] == "1200.00"

# --- POST /api/family/{family_id}/child/{child_id}/provider/{provider_id}/allocation/{month}/{year}/submit ---
def test_submit_care_days_success(client, seed_db, mocker):
    allocation, care_day_new, care_day_submitted, care_day_needs_resubmission, care_day_locked, care_day_deleted = seed_db
    mock_send_notification = mocker.patch('app.routes.family.send_submission_notification')

    response = client.post(f'/api/family/1/child/{allocation.google_sheets_child_id}/provider/{care_day_new.provider_google_sheets_id}/allocation/{allocation.date.month}/{allocation.date.year}/submit')
    assert response.status_code == 200
    assert response.json['message'] == 'Submission successful'

    # Verify new, modified, and removed days are in the response
    assert len(response.json['new_days']) == 1 # care_day_new
    assert response.json['new_days'][0]['id'] == care_day_new.id
    assert len(response.json['modified_days']) == 1 # care_day_needs_resubmission
    assert response.json['modified_days'][0]['id'] == care_day_needs_resubmission.id
    assert len(response.json['removed_days']) == 1 # care_day_deleted
    assert response.json['removed_days'][0]['id'] == care_day_deleted.id

    # Verify send_submission_notification was called
    mock_send_notification.assert_called_once()
    args, kwargs = mock_send_notification.call_args
    assert args[0] == care_day_new.provider_google_sheets_id # provider_id
    assert args[1] == allocation.google_sheets_child_id # child_id
    assert len(args[2]) == 1 # new_days
    assert len(args[3]) == 1 # modified_days
    assert len(args[4]) == 1 # removed_days

    # Verify last_submitted_at is updated for submitted days
    with client.application.app_context():
        updated_new_day = AllocatedCareDay.query.get(care_day_new.id)
        updated_needs_resubmission_day = AllocatedCareDay.query.get(care_day_needs_resubmission.id)
        assert updated_new_day.last_submitted_at is not None
        assert updated_needs_resubmission_day.last_submitted_at is not None

def test_submit_care_days_no_care_days(client, seed_db, mocker):
    _, _, _, _, _, _ = seed_db
    mock_send_notification = mocker.patch('app.routes.family.send_submission_notification')

    # Create a new allocation with no care days
    new_allocation_child_id = 2
    new_allocation_month = 2
    new_allocation_year = 2024

    with client.application.app_context():
        new_allocation = MonthAllocation(
            date=date(new_allocation_year, new_allocation_month, 1),
            allocation_dollars=500,
            allocation_days=5,
            google_sheets_child_id=new_allocation_child_id
        )
        db.session.add(new_allocation)
        db.session.commit()

    response = client.post(f'/api/family/1/child/{new_allocation_child_id}/provider/1/allocation/{new_allocation_month}/{new_allocation_year}/submit')
    assert response.status_code == 200
    assert response.json['message'] == 'Submission successful'
    assert len(response.json['new_days']) == 0
    assert len(response.json['modified_days']) == 0
    assert len(response.json['removed_days']) == 0
    mock_send_notification.assert_called_once()

def test_submit_care_days_allocation_not_found(client, seed_db, mocker):
    _, _, _, _, _, _ = seed_db
    mock_send_notification = mocker.patch('app.routes.family.send_submission_notification')

    response = client.post('/api/family/1/child/999/provider/1/allocation/1/2024/submit') # Non-existent child
    assert response.status_code == 404
    assert 'Allocation not found' in response.json['error']
    mock_send_notification.assert_not_called()
