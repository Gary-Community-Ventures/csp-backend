import uuid
from datetime import datetime, timezone

from ..extensions import db
from .mixins import TimestampMixin


class Attendance(db.Model, TimestampMixin):
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    week = db.Column(db.Date, nullable=False, index=True)
    child_google_sheet_id = db.Column(db.String(64), index=True)
    provider_google_sheet_id = db.Column(db.String(64), index=True)
    family_entered_hours = db.Column(db.Integer, nullable=True)
    family_entered_at = db.Column(db.DateTime, nullable=True)
    provider_entered_hours = db.Column(db.Integer, nullable=True)
    provider_entered_at = db.Column(db.DateTime, nullable=True)
    family_opened_at = db.Column(db.DateTime, nullable=True)
    provider_opened_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<Attendance {self.id} - Child: {self.child_google_sheet_id} - Provider: {self.provider_google_sheet_id}>"
        )

    @staticmethod
    def new(child_id: str, provider_id: str):
        return Attendance(
            week=datetime.now(timezone.utc).date(), child_google_sheet_id=child_id, provider_google_sheet_id=provider_id
        )

    def family_entered(self, hours: int):
        self.family_entered_hours = hours
        self.family_entered_at = datetime.now(timezone.utc)

        return self

    def provider_entered(self, hours: int):
        self.provider_entered_hours = hours
        self.provider_entered_at = datetime.now(timezone.utc)

        return self

    def record_family_opened(self):
        self.family_opened_at = datetime.now(timezone.utc)

        return self

    def record_provider_opened(self):
        self.provider_opened_at = datetime.now(timezone.utc)

        return self

    @classmethod
    def filter_by_child_ids(cls, child_ids: list[str]):
        return cls.query.filter(cls.child_google_sheet_id.in_(child_ids), cls.family_entered_hours.is_(None))

    @classmethod
    def filter_by_provider_id(cls, provider_id: str):
        return cls.query.filter(cls.provider_google_sheet_id == provider_id, cls.provider_entered_hours.is_(None))
