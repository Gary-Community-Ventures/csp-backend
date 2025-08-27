from ..extensions import db


class TimestampMixin:
    """A mixin for created_at and updated_at timestamps."""

    __abstract__ = True  # This is an abstract mixin, not a standalone model

    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), nullable=False
    )
