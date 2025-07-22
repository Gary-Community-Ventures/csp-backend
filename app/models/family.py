from ..extensions import db
from .mixins import TimestampMixin


class Family(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)

    google_sheet_id = db.Column(db.String(64), unique=True, nullable=True, index=True)

    def __repr__(self):
        return f"<Family {self.id} - Google Sheet ID: {self.google_sheet_id}>"

    @staticmethod
    def new(google_sheet_id: str):
        return Family(
            google_sheet_id=google_sheet_id,
        )
