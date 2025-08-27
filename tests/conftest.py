from datetime import date
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from app import create_app
from app.extensions import db
from app.models.month_allocation import MonthAllocation


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture(autouse=True)
def mock_send_submission_notification(mocker: MockerFixture):
    # Mock the email notification that's sent after payment processing
    mock = mocker.patch("app.routes.child.send_care_days_payment_request_email")
    return mock


@pytest.fixture(autouse=True)
def mock_payment_service(mocker: MockerFixture):
    # Mock the payment service process_payment method
    mock = mocker.patch("app.routes.child.current_app.payment_service.process_payment")
    mock.return_value = True  # Assume payment succeeds by default
    return mock


@pytest.fixture(autouse=True)
def mock_clerk_authentication(mocker: MockerFixture):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {
        "sub": "user_id_123",
        "sid": "session_id_123",
        "data": {"types": ["family"], "family_id": "family123", "provider_id": None},
    }
    # Patch the authenticate_request method of the Clerk class
    mocker.patch("clerk_backend_api.Clerk.authenticate_request", return_value=mock_request_state)


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
        }
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_get_child():
    with patch("app.models.month_allocation.get_child") as mock:
        yield mock


@pytest.fixture
def month_allocation(db_session):
    allocation = MonthAllocation(
        google_sheets_child_id="1",
        date=date.today().replace(day=1),
        allocation_cents=100000,
    )
    db_session.add(allocation)
    db_session.commit()
    return allocation
