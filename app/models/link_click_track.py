import uuid
from typing import Optional

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

    @staticmethod
    def get_by_provider(provider_id: str, link: str) -> Optional["LinkClickTrack"]:
        """Get existing link click track or create a new one"""
        track = LinkClickTrack.query.filter_by(provider_supabase_id=provider_id, link=link).first()

        if track:
            return track
        else:
            return None

    @staticmethod
    def get_by_family(family_id: str, link: str) -> Optional["LinkClickTrack"]:
        """Get existing link click track by family ID or create a new one"""
        track = LinkClickTrack.query.filter_by(family_supabase_id=family_id, link=link).first()

        if track:
            return track
        else:
            return None

    @staticmethod
    def create(provider_id: str | None, family_id: str | None, link: str):
        """Create a new link click track"""
        track = LinkClickTrack(
            provider_supabase_id=provider_id,
            family_supabase_id=family_id,
            link=link,
        )
        return track

    def __repr__(self):
        return f"<LinkClickTrack {self.id} - Link: {self.link} - Clicks: {self.click_count} - Provider: {self.provider_supabase_id} - Family: {self.family_supabase_id}>"
