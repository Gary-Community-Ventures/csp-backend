import pytest
from app.models import PaymentRate
from app.extensions import db


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
        db.session.commit()

        yield payment_rate


# Mock the authentication for all tests in this file
@pytest.fixture(autouse=True)
def mock_authentication(mocker):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {"data": {"types": ["family"], "family_id": 1}}
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)


# --- POST /payment-rates ---
def test_create_payment_rate_success(client):
    response = client.post(
        "/payment-rates",
        json={
            "provider_id": 2,
            "child_id": 2,
            "half_day_rate": 30000,
            "full_day_rate": 50000,
        },
    )
    assert response.status_code == 201
    assert response.json["google_sheets_provider_id"] == 2
    assert response.json["google_sheets_child_id"] == 2
    assert response.json["half_day_rate_cents"] == 30000
    assert response.json["full_day_rate_cents"] == 50000


def test_create_payment_rate_missing_fields(client):
    response = client.post(
        "/payment-rates",
        json={
            "provider_id": 2,
            "child_id": 2,
            "half_day_rate": 30000,
        },
    )
    assert response.status_code == 400
    assert "Missing required fields" in response.json["error"]


def test_create_payment_rate_already_exists(client, seed_db):
    response = client.post(
        "/payment-rates",
        json={
            "provider_id": 1,
            "child_id": 1,
            "half_day_rate": 30000,
            "full_day_rate": 50000,
        },
    )
    assert response.status_code == 400
    assert "Payment rate already exists" in response.json["error"]


# --- GET /payment-rates/<provider_id>/<child_id> ---
def test_get_payment_rate_success(client, seed_db):
    response = client.get("/payment-rates/1/1")
    assert response.status_code == 200
    assert response.json["google_sheets_provider_id"] == 1
    assert response.json["google_sheets_child_id"] == 1
    assert response.json["half_day_rate_cents"] == 40000
    assert response.json["full_day_rate_cents"] == 60000


def test_get_payment_rate_not_found(client):
    response = client.get("/payment-rates/2/2")
    assert response.status_code == 404
    assert "Payment rate not found" in response.json["error"]


# --- PUT /payment-rates/<provider_id>/<child_id> ---
def test_update_payment_rate_success(client, seed_db):
    response = client.put(
        "/payment-rates/1/1",
        json={"half_day_rate": 35000, "full_day_rate": 55000},
    )
    assert response.status_code == 200
    assert response.json["half_day_rate_cents"] == 35000
    assert response.json["full_day_rate_cents"] == 55000


def test_update_payment_rate_not_found(client):
    response = client.put(
        "/payment-rates/2/2",
        json={"half_day_rate": 35000, "full_day_rate": 55000},
    )
    assert response.status_code == 404
    assert "Payment rate not found" in response.json["error"]
