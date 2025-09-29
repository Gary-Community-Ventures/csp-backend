"""Merge attendance_days and email_record branches

Revision ID: 05706026adc8
Revises: d458ce0f02ff, e7f96bcb63e2
Create Date: 2025-09-26 22:38:34.208833

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "05706026adc8"
down_revision = ("d458ce0f02ff", "e7f96bcb63e2")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
