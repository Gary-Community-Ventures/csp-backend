import uuid

from sqlalchemy.orm import Query

from ..extensions import db
from .mixins import TimestampMixin


class FamilyInvitation(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.UUID(as_uuid=True), index=True)
    provider_google_sheet_id = db.Column(db.String(64), nullable=True, index=True)
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    invite_email = db.Column(db.String(254), nullable=False)
    email_sent = db.Column(db.Boolean(), default=False, nullable=False)
    sms_sent = db.Column(db.Boolean(), default=False, nullable=False)
    accepted = db.Column(db.Boolean(), default=False, nullable=False)
    opened_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<FamilyInvitation {self.id} - Provider Sheet ID: {self.provider_supabase_id}>"

    @staticmethod
    def new(public_id: str, invite_email: str, provider_id: int):
        return FamilyInvitation(
            public_id=public_id,
            invite_email=invite_email,
            provider_supabase_id=provider_id,
        )

    @classmethod
    def invitation_by_id(cls, id: str) -> Query:
        try:
            uuid.UUID(id)
        except (ValueError, AttributeError):
            return cls.query.filter(False)

        return cls.query.filter_by(public_id=id)

    def record_email_sent(self):
        self.email_sent = True

        return self

    def record_sms_sent(self):
        self.sms_sent = True

        return self

    def record_opened(self):
        self.opened_at = db.func.now()

        return self

    def record_accepted(self):
        self.accepted = True

        return self
