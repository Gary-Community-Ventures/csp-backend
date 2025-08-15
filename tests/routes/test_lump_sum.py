from datetime import date

import pytest

from app.extensions import db
from app.models import AllocatedLumpSum, MonthAllocation
from app.schemas.lump_sum import AllocatedLumpSumResponse
from app.sheets.mappings import ChildColumnNames, ProviderColumnNames


# Fixture to set up test data
@pytest.fixture
def seed_lump_sum_db(app):
    with app.app_context():
        # Create a MonthAllocation for testing
        allocation = MonthAllocation(
            date=date.today().replace(day=1),
            allocation_cents=100000,  # 1000.00
            google_sheets_child_id="child123",
        )
        db.session.add(allocation)
        db.session.commit()
        yield allocation


# Mock Google Sheets data functions
@pytest.fixture
def mock_sheets_data(mocker):
    # Mock get_children
    mocker.patch(
        "app.routes.lump_sum.get_children",
        return_value=[
            {
                ChildColumnNames.ID: "child123",
                ChildColumnNames.FAMILY_ID: "family123",
                ChildColumnNames.FIRST_NAME: "Test",
                ChildColumnNames.LAST_NAME: "Child",
            },
            {
                ChildColumnNames.ID: "child456",
                ChildColumnNames.FAMILY_ID: "family456",
                ChildColumnNames.FIRST_NAME: "Another",
                ChildColumnNames.LAST_NAME: "Child",
            },
        ],
    )
    # Mock get_family_children
    mocker.patch(
        "app.routes.lump_sum.get_family_children",
        side_effect=lambda family_id, children_data: [
            c for c in children_data if c.get(ChildColumnNames.FAMILY_ID) == family_id
        ],
    )
    # Mock get_provider_child_mappings
    mocker.patch(
        "app.routes.lump_sum.get_provider_child_mappings",
        return_value=[
            {"child_id": "child123", "provider_id": "providerABC"},
            {"child_id": "child123", "provider_id": "providerXYZ"},
            {"child_id": "child456", "provider_id": "providerDEF"},
        ],
    )
    # Mock get_providers
    mocker.patch(
        "app.routes.lump_sum.get_providers",
        return_value=[
            {ProviderColumnNames.ID: "providerABC", ProviderColumnNames.NAME: "Provider A"},
            {ProviderColumnNames.ID: "providerXYZ", ProviderColumnNames.NAME: "Provider X"},
            {ProviderColumnNames.ID: "providerDEF", ProviderColumnNames.NAME: "Provider D"},
        ],
    )
    # Mock get_child_providers
    mocker.patch(
        "app.routes.lump_sum.get_child_providers",
        side_effect=lambda child_id, mappings, providers: [
            p
            for p in providers
            if p.get(ProviderColumnNames.ID)
            in [m.get("provider_id") for m in mappings if m.get("child_id") == child_id]
        ],
    )


# --- POST /lump-sums ---


def test_create_lump_sum_success(client, seed_lump_sum_db, mock_sheets_data, mocker):
    allocation = seed_lump_sum_db
    mock_send_email = mocker.patch("app.routes.lump_sum.send_lump_sum_payment_request_email")

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 50000,  # 500.00
        },
    )
    assert response.status_code == 201
    validated_response = AllocatedLumpSumResponse.model_validate(response.json)
    assert validated_response.amount_cents == 50000
    assert validated_response.provider_google_sheets_id == "providerABC"
    assert validated_response.care_month_allocation_id == allocation.id
    assert validated_response.submitted_at is not None

    mock_send_email.assert_called_once_with(
        provider_name="Provider A",
        google_sheets_provider_id="providerABC",
        child_first_name="Test",
        child_last_name="Child",
        google_sheets_child_id="child123",
        amount_in_cents=50000,
        month=allocation.date.strftime("%B %Y"),
    )

    with client.application.app_context():
        lump_sum = AllocatedLumpSum.query.filter_by(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id="providerABC",
            amount_cents=50000,
        ).first()
        assert lump_sum is not None
        assert lump_sum.submitted_at is not None


def test_create_lump_sum_missing_fields(client, seed_lump_sum_db, mock_sheets_data):
    allocation = seed_lump_sum_db

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            # Missing amount_cents
        },
    )
    assert response.status_code == 400
    assert "Missing required fields" in response.json["error"]


def test_create_lump_sum_allocation_not_found(client, mock_sheets_data):

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": 999,  # Non-existent ID
            "provider_id": "providerABC",
            "amount_cents": 10000,
        },
    )
    assert response.status_code == 404
    assert "MonthAllocation not found" in response.json["error"]


def test_create_lump_sum_child_not_associated_with_family(client, seed_lump_sum_db, mock_sheets_data, mocker):
    allocation = seed_lump_sum_db
    # Mock get_children to return a child not associated with the authenticated family
    mocker.patch(
        "app.routes.lump_sum.get_children",
        return_value=[
            {ChildColumnNames.ID: "child999", ChildColumnNames.FAMILY_ID: "family999"},
        ],
    )

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 10000,
        },
    )
    assert response.status_code == 403
    assert "Child not associated with the authenticated family." in response.json["error"]


def test_create_lump_sum_provider_not_associated_with_child(client, seed_lump_sum_db, mock_sheets_data, mocker):
    allocation = seed_lump_sum_db
    # Mock get_provider_child_mappings to exclude providerABC for child123
    mocker.patch(
        "app.routes.lump_sum.get_provider_child_mappings",
        return_value=[
            {"child_id": "child123", "provider_id": "providerXYZ"},  # Only XYZ for child123
        ],
    )

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",  # This provider is not associated with child123 in the mock
            "amount_cents": 10000,
        },
    )
    assert response.status_code == 403
    assert "Provider not associated with the specified child." in response.json["error"]


def test_create_lump_sum_exceeds_allocation(client, seed_lump_sum_db, mock_sheets_data):
    allocation = seed_lump_sum_db

    response = client.post(
        "/lump-sums",
        json={
            "allocation_id": allocation.id,
            "provider_id": "providerABC",
            "amount_cents": 150000,  # Exceeds 100000 allocation
        },
    )
    assert response.status_code == 400
    assert "Adding this lump sum would exceed monthly allocation" in response.json["error"]
