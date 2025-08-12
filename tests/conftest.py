import pytest
from pytest_mock import MockerFixture
from app import create_app
from app.extensions import db
from app.models.month_allocation import MonthAllocation
from app.models.allocated_care_day import AllocatedCareDay
from unittest.mock import patch
from datetime import date


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture(autouse=True)
def mock_send_submission_notification(mocker: MockerFixture):
    mock = mocker.patch("app.routes.child.send_submission_notification")
    return mock


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
