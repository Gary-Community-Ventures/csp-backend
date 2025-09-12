from datetime import date

import pytest
from pytest_mock import MockerFixture

from app import create_app
from app.extensions import db
from app.models.month_allocation import MonthAllocation
from tests.supabase_mocks import create_mock_supabase_client, setup_standard_test_data


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture(autouse=True)
def mock_payment_service(mocker: MockerFixture):
    # Mock the payment service methods used across the app
    mock_process = mocker.patch("app.routes.child.current_app.payment_service.process_payment")
    mock_process.return_value = True  # Assume payment succeeds by default

    # Mock allocate_funds_to_family used in MonthAllocation
    from datetime import datetime, timezone

    mock_allocate = mocker.patch("app.models.month_allocation.current_app.payment_service.allocate_funds_to_family")
    mock_allocate.return_value = mocker.Mock(
        transfer=mocker.Mock(
            id="test-transfer-123", created=datetime.now(timezone.utc)  # Provide a real datetime instead of Mock
        )
    )

    # Mock refresh_provider_settings used in provider_payment_settings
    mock_refresh = mocker.patch(
        "app.models.provider_payment_settings.current_app.payment_service.refresh_provider_settings"
    )
    mock_refresh.return_value = None

    # Mock refresh_family_settings used in family_payment_settings
    mock_refresh_family = mocker.patch(
        "app.models.family_payment_settings.current_app.payment_service.refresh_family_settings"
    )
    mock_refresh_family.return_value = None

    return {
        "process_payment": mock_process,
        "allocate_funds_to_family": mock_allocate,
        "refresh_provider_settings": mock_refresh,
        "refresh_family_settings": mock_refresh_family,
    }


@pytest.fixture(autouse=True)
def mock_clerk_authentication(mocker: MockerFixture):
    mock_request_state = mocker.Mock()
    mock_request_state.is_signed_in = True
    mock_request_state.payload = {
        "sub": "user_id_123",
        "sid": "session_id_123",
        "data": {"types": ["family"], "family_id": "family123", "provider_id": None},
    }
    # Mock at the decorator level to bypass Clerk client check
    # This works regardless of whether CLERK_SECRET_KEY is set
    mocker.patch("app.auth.decorators._authenticate_request", return_value=mock_request_state)


@pytest.fixture
def mock_supabase(mocker: MockerFixture):
    """Mock Supabase client with standard test data."""
    mock_client = create_mock_supabase_client(setup_standard_test_data())
    return mock_client


@pytest.fixture
def app(mock_supabase):
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
        }
    )
    
    # Set the mock Supabase client
    app.supabase_client = mock_supabase

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def month_allocation(db_session):
    allocation = MonthAllocation(
        child_supabase_id="1",
        date=date.today().replace(day=1),
        allocation_cents=100000,
    )
    db_session.add(allocation)
    db_session.commit()
    return allocation
