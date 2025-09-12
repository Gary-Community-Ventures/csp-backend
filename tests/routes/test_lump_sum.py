from datetime import date

import pytest

from app.extensions import db
from app.models import AllocatedLumpSum, MonthAllocation
from app.schemas.lump_sum import AllocatedLumpSumResponse


# Fixture to set up test data
@pytest.fixture
def seed_lump_sum_db(app):
    with app.app_context():
        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=100000,  # 1000.00
            child_supabase_id="child123",
        )
        db.session.add(allocation)
        db.session.commit()
        yield allocation


@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"sub": "1234", "data": {"types": ["family"], "family_id": 123}}
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)
    
    # Mock get_family_user
    mock_user = mocker.Mock()
    mock_user.user_data.family_id = 123
    mocker.patch("app.routes.lump_sum.get_family_user", return_value=mock_user)


# --- POST /lump-sums ---


def test_create_lump_sum_success(client, seed_lump_sum_db, mocker, app):
    allocation = seed_lump_sum_db
    mock_send_email = mocker.patch("app.routes.lump_sum.send_lump_sum_payment_email")
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Override the default data with our test-specific data
    child_data = create_mock_child_data(child_id="child123", family_id=123, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    
    # Set up the join data structure that Child.select_by_family_id would return
    # Provider.unwrap expects the data to have a "provider" key
    child_data["provider"] = [provider_data]
    
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 50000,  # 500.00
            "hours": 10.5,
        },
    )
    assert response.status_code == 201
    validated_response = AllocatedLumpSumResponse.model_validate(response.json)
    assert validated_response.amount_cents == 50000
    assert validated_response.provider_supabase_id == "providerABC"
    assert validated_response.care_month_allocation_id == allocation.id
    assert validated_response.submitted_at is not None

    # Verify mock was called
    mock_send_email.assert_called_once()

    with client.application.app_context():
        lump_sum = AllocatedLumpSum.query.filter_by(
            care_month_allocation_id=allocation.id,
            provider_supabase_id="providerABC",
            amount_cents=50000,
            hours=10.5,
        ).first()
        assert lump_sum is not None
        assert lump_sum.submitted_at is not None


def test_create_lump_sum_missing_cents(client, seed_lump_sum_db):
    allocation = seed_lump_sum_db

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "hours": 10.5,
            # Missing amount_cents
        },
    )
    assert response.status_code == 400
    assert any("amount_cents" in err["loc"] for err in response.json["error"])


def test_create_lump_sum_missing_hours(client, seed_lump_sum_db):
    allocation = seed_lump_sum_db

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 50000,  # 500.00
            # Missing hours
        },
    )
    assert response.status_code == 400
    assert any("hours" in err["loc"] for err in response.json["error"])


def test_create_lump_sum_allocation_not_found(client):

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": 999,  # Non-existent ID
            "provider_id": "providerABC",
            "amount_cents": 10000,
            "hours": 5.0,
        },
    )
    assert response.status_code == 404
    assert "MonthAllocation not found" in response.json["error"]


def test_create_lump_sum_child_not_associated_with_family(client, seed_lump_sum_db, app):
    allocation = seed_lump_sum_db
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Child is associated with a different family
    child_data = create_mock_child_data(child_id="child123", family_id=999, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    child_data["provider"] = [provider_data]
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 10000,
            "hours": 5.0,
        },
    )
    assert response.status_code == 403
    assert "Child not associated with the authenticated family." in response.json["error"]


def test_create_lump_sum_provider_not_associated_with_child(client, seed_lump_sum_db, app):
    allocation = seed_lump_sum_db
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Child is in the family but provider is not associated with the child
    child_data = create_mock_child_data(child_id="child123", family_id=123, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    # Don't include the provider in the child's provider list
    child_data["provider"] = []
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",  # This provider is not associated with child123
            "amount_cents": 10000,
            "hours": 5.0,
        },
    )
    assert response.status_code == 403
    assert "Provider not associated with the specified child." in response.json["error"]


def test_create_lump_sum_exceeds_allocation(client, seed_lump_sum_db, app):
    allocation = seed_lump_sum_db
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Setup valid child and provider
    child_data = create_mock_child_data(child_id="child123", family_id=123, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    child_data["provider"] = [provider_data]
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 130000,  # Exceeds 100000 allocation
            "hours": 5.0,
        },
    )
    assert response.status_code == 400
    assert "Adding this lump sum would exceed monthly allocation" in response.json["error"]


def test_create_lump_sum_exceeds_max_allowable_amount(client, seed_lump_sum_db, app):
    allocation = seed_lump_sum_db
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Setup valid child and provider
    child_data = create_mock_child_data(child_id="child123", family_id=123, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    child_data["provider"] = [provider_data]
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 150000,  # Exceeds 100000 allocation
            "hours": 5.0,
        },
    )
    assert response.status_code == 400
    assert "Lump sum amount $1500.00 exceeds maximum allowed payment of $1400.00" in response.json["error"]


def test_create_lump_sum_hours_negative(client, seed_lump_sum_db, app):
    allocation = seed_lump_sum_db
    
    # Add specific test data to the mock Supabase client
    from tests.supabase_mocks import create_mock_child_data, create_mock_provider_data
    
    # Setup valid child and provider
    child_data = create_mock_child_data(child_id="child123", family_id=123, payment_enabled=True)
    provider_data = create_mock_provider_data(provider_id="providerABC", payment_enabled=True)
    child_data["provider"] = [provider_data]
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 150000,  # Exceeds 100000 allocation
            "hours": -5.0,
        },
    )
    assert response.status_code == 400
    assert "Hours must be a positive float" in response.json["error"]
