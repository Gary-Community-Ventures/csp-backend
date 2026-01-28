import uuid

from sqlalchemy.dialects.postgresql import UUID

from ..extensions import db
from .mixins import TimestampMixin


class LinkClickTrack(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)

    click_count = db.Column(db.Integer, nullable=False, default=1)
    link = db.Column(db.String(2048), nullable=False)

    # Either provider_supabase_id or family_supabase_id will be set
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    family_supabase_id = db.Column(db.String(64), nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("provider_supabase_id", "link", name="link_provider"),
        db.UniqueConstraint("family_supabase_id", "link", name="link_family"),
    )

    def __repr__(self):
        return f"<LinkClickTrack {self.id} - Link: {self.link} - Clicks: {self.click_count} - Provider: {self.provider_supabase_id} - Family: {self.family_supabase_id}>"
