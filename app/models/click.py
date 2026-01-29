import uuid
from typing import Optional

from sqlalchemy.dialects.postgresql import UUID

from ..extensions import db
from .mixins import TimestampMixin


class Click(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)

    tracking_id = db.Column(db.String(128), nullable=True, index=True)
    click_count = db.Column(db.Integer, nullable=False, default=1)

    # Optional URL associated with the click
    url = db.Column(db.String(2048), nullable=True)

    # Either provider_supabase_id or family_supabase_id will be set
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    family_supabase_id = db.Column(db.String(64), nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("provider_supabase_id", "tracking_id", name="tracking_id_provider"),
        db.UniqueConstraint("family_supabase_id", "tracking_id", name="tracking_id_family"),
    )

    @staticmethod
    def get_by_provider(provider_id: str, tracking_id: str) -> Optional["Click"]:
        """Get existing click by provider ID and tracking ID"""
        return Click.query.filter_by(provider_supabase_id=provider_id, tracking_id=tracking_id).first()

    @staticmethod
    def get_by_family(family_id: str, tracking_id: str) -> Optional["Click"]:
        """Get existing click by family ID and tracking ID"""
        return Click.query.filter_by(family_supabase_id=family_id, tracking_id=tracking_id).first()

    @staticmethod
    def create(provider_id: str | None, family_id: str | None, tracking_id: str, url: str | None = None) -> "Click":
        """Create a new click"""
        click = Click(
            provider_supabase_id=provider_id,
            family_supabase_id=family_id,
            tracking_id=tracking_id,
            url=url,
        )
        return click

    def __repr__(self):
        return f"<Click {self.id} - Tracking ID: {self.tracking_id} - Clicks: {self.click_count} - Provider: {self.provider_supabase_id} - Family: {self.family_supabase_id}>"
