import pytest

from app.extensions import db
from app.models import PaymentRate


@pytest.fixture
def seed_db(app):
    with app.app_context():
        # Create a PaymentRate for testing (using valid values within MIN_PAYMENT_RATE and MAX_PAYMENT_RATE)
        payment_rate = PaymentRate(
            provider_supabase_id="1",
            child_supabase_id="1",
            full_day_rate_cents=5000,  # $50
            half_day_rate_cents=4000,  # $40
        )
        db.session.add(payment_rate)
        db.session.commit()

        yield payment_rate


# Override the global mock_clerk_authentication for our tests
@pytest.fixture(autouse=True)
def mock_auth_and_helpers(mocker, request, app):
    # Mock _authenticate_request directly to bypass Clerk client check
    # Determine which type of auth to use based on test name
    mocker.patch("app.routes.payment_rate.send_new_payment_rate_email", return_value=True)
    if "get_payment_rate" in request.node.name:
        # Family auth for GET endpoints
        mock_request_state = mocker.Mock()
        mock_request_state.is_signed_in = True
        mock_request_state.payload = {
            "sub": "user_id_123",
            "sid": "session_id_123",
            "data": {"types": ["family"], "family_id": "1"},
        }
        # Mock at the decorator level to bypass Clerk client check
        mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)

        # Mock get_family_user
        mock_user = mocker.Mock()
        mock_user.user_data.family_id = "1"
        mocker.patch("app.routes.payment_rate.get_family_user", return_value=mock_user)

        children = [
            {"ID": "1", "Family ID": "1"},
            {"ID": "2", "Family ID": "1"},
        ]
        mocker.patch(
            "app.routes.payment_rate.get_children",
            return_value=children,
        )
        mocker.patch(
            "app.routes.payment_rate.get_family_children",
            return_value=children,
        )
    else:
        # Provider auth for POST endpoints
        mock_request_state = mocker.Mock()
        mock_request_state.is_signed_in = True
        mock_request_state.payload = {
            "sub": "user_id_123",
            "sid": "session_id_123",
            "data": {"types": ["provider"], "provider_id": "1"},
        }
        # Mock at the decorator level to bypass Clerk client check
        mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)

        # Mock get_provider_user
        mock_user = mocker.Mock()
        mock_user.user_data.provider_id = "1"
        mocker.patch("app.routes.payment_rate.get_provider_user", return_value=mock_user)

    # Mock get_provider_child_mappings for all tests

    mappings = [
        {"Child ID": "1", "Provider ID": "1"},
        {"Child ID": "2", "Provider ID": "1"},
        {"Child ID": "3", "Provider ID": "1"},
        {"Child ID": "2", "Provider ID": "2"},
    ]
    mocker.patch(
        "app.routes.payment_rate.get_provider_child_mappings",
        return_value=mappings,
    )


# --- POST /payment-rates/<child_id> ---
def test_create_payment_rate_success(client, app):
    response = client.post(
        "/payment-rates/2",
        json={
            "half_day_rate_cents": 3000,  # $30 - within valid range
            "full_day_rate_cents": 5000,  # $50 - within valid range
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201
    # Response only has id and the rate cents, not provider/child IDs based on PaymentRateResponse schema
    assert response.json["half_day_rate_cents"] == 3000
    assert response.json["full_day_rate_cents"] == 5000
    assert "id" in response.json


def test_create_payment_rate_missing_fields(client):
    response = client.post(
        "/payment-rates/2",
        json={
            "half_day_rate_cents": 3000,  # $30 - within valid range
            # Missing full_day_rate_cents
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 400
    assert response.json["error"][0]["loc"] == ["full_day_rate_cents"]
    assert "Field required" in response.json["error"][0]["msg"]


def test_create_payment_rate_already_exists(client, seed_db):
    response = client.post(
        "/payment-rates/1",
        json={
            "half_day_rate_cents": 3000,  # $30 - within valid range
            "full_day_rate_cents": 5000,  # $50 - within valid range
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 400
    assert "Payment rate already exists" in response.json["error"]


# --- GET /payment-rates/<provider_id>/<child_id> ---
def test_get_payment_rate_success(client, seed_db):
    response = client.get("/payment-rates/1/1", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    # Response only has id and the rate cents based on PaymentRateResponse schema
    assert response.json["half_day_rate_cents"] == 4000  # $40 from seed_db
    assert response.json["full_day_rate_cents"] == 5000  # $50 from seed_db
    assert "id" in response.json


def test_get_payment_rate_not_found(client):
    response = client.get("/payment-rates/2/2", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 404
    assert "Payment rate not found" in response.json["error"]


def test_create_payment_rate_invalid_values(client):
    # Test with half_day_rate_cents = 0 (less than MIN_PAYMENT_RATE of 100)
    response = client.post(
        "/payment-rates/3",
        json={
            "half_day_rate_cents": 0,
            "full_day_rate_cents": 5000,  # $50 - within valid range
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 400
    assert response.json["error"][0]["loc"] == ["half_day_rate_cents"]
    assert "greater than or equal to 100" in response.json["error"][0]["msg"]
