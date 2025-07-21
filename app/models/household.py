from ..extensions import db
from .mixins import TimestampMixin


class Household(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)

    google_sheet_id = db.Column(
        db.String(64), unique=True, nullable=True, index=True
    )
    
    def __repr__(self):
        return f"<Household {self.id} - Google Sheet ID: {self.google_sheet_id}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "google_sheet_id": self.google_sheet_id,
        }

    @staticmethod
    def from_dict(data):
        return Household(
            google_sheet_id=data.get("google_sheet_id"),
        )
