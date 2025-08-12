"""Update google sheet ids to be strings

Revision ID: c7037570b095
Revises: ff81a8277415
Create Date: 2025-08-07 14:47:50.375451

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import MetaData, Table
from sqlalchemy.orm import sessionmaker

# revision identifiers, used by Alembic.
revision = "c7037570b095"
down_revision = "ff81a8277415"
branch_labels = None
depends_on = None


def upgrade():
    # Get database connection and create session
    connection = op.get_bind()
    Session = sessionmaker(bind=connection)
    session = Session()

    # Define table structures for the migration
    metadata = MetaData()

    # First, add temporary string columns
    with op.batch_alter_table("allocated_care_day", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_google_sheets_id_temp", sa.String(length=64)))

    with op.batch_alter_table("month_allocation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.String(length=64)))

    with op.batch_alter_table("payment_rate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_provider_id_temp", sa.String(length=64)))
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.String(length=64)))

    with op.batch_alter_table("payment_request", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_provider_id_temp", sa.String(length=64)))
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.String(length=64)))

    # Reflect the current table structures after adding temp columns
    metadata.reflect(bind=connection)

    allocated_care_day = metadata.tables["allocated_care_day"]
    month_allocation = metadata.tables["month_allocation"]
    payment_rate = metadata.tables["payment_rate"]
    payment_request = metadata.tables["payment_request"]

    # Convert data using ORM-style updates
    try:
        # Update allocated_care_day
        session.execute(
            allocated_care_day.update()
            .values(
                provider_google_sheets_id_temp=sa.func.cast(allocated_care_day.c.provider_google_sheets_id, sa.String)
            )
            .where(allocated_care_day.c.provider_google_sheets_id.isnot(None))
        )

        # Update month_allocation
        session.execute(
            month_allocation.update()
            .values(google_sheets_child_id_temp=sa.func.cast(month_allocation.c.google_sheets_child_id, sa.String))
            .where(month_allocation.c.google_sheets_child_id.isnot(None))
        )

        # Update payment_rate
        session.execute(
            payment_rate.update()
            .values(google_sheets_provider_id_temp=sa.func.cast(payment_rate.c.google_sheets_provider_id, sa.String))
            .where(payment_rate.c.google_sheets_provider_id.isnot(None))
        )
        session.execute(
            payment_rate.update()
            .values(google_sheets_child_id_temp=sa.func.cast(payment_rate.c.google_sheets_child_id, sa.String))
            .where(payment_rate.c.google_sheets_child_id.isnot(None))
        )

        # Update payment_request
        session.execute(
            payment_request.update()
            .values(google_sheets_provider_id_temp=sa.func.cast(payment_request.c.google_sheets_provider_id, sa.String))
            .where(payment_request.c.google_sheets_provider_id.isnot(None))
        )
        session.execute(
            payment_request.update()
            .values(google_sheets_child_id_temp=sa.func.cast(payment_request.c.google_sheets_child_id, sa.String))
            .where(payment_request.c.google_sheets_child_id.isnot(None))
        )

        # Commit the data updates
        session.commit()

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    # Drop old columns and rename temp columns
    with op.batch_alter_table("allocated_care_day", schema=None) as batch_op:
        batch_op.drop_column("provider_google_sheets_id")
        batch_op.alter_column(
            "provider_google_sheets_id_temp",
            new_column_name="provider_google_sheets_id",
            nullable=False,
        )

    with op.batch_alter_table("month_allocation", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_child_id")
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )

    with op.batch_alter_table("payment_rate", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_provider_id")
        batch_op.drop_column("google_sheets_child_id")
        batch_op.alter_column(
            "google_sheets_provider_id_temp",
            new_column_name="google_sheets_provider_id",
            nullable=False,
        )
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )

    with op.batch_alter_table("payment_request", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_provider_id")
        batch_op.drop_column("google_sheets_child_id")
        batch_op.alter_column(
            "google_sheets_provider_id_temp",
            new_column_name="google_sheets_provider_id",
            nullable=False,
        )
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )


def downgrade():
    # Get database connection and create session
    connection = op.get_bind()
    Session = sessionmaker(bind=connection)
    session = Session()

    # Add temporary integer columns
    with op.batch_alter_table("payment_request", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.INTEGER()))
        batch_op.add_column(sa.Column("google_sheets_provider_id_temp", sa.INTEGER()))

    with op.batch_alter_table("payment_rate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.INTEGER()))
        batch_op.add_column(sa.Column("google_sheets_provider_id_temp", sa.INTEGER()))

    with op.batch_alter_table("month_allocation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sheets_child_id_temp", sa.INTEGER()))

    with op.batch_alter_table("allocated_care_day", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_google_sheets_id_temp", sa.INTEGER()))

    # Reflect the current table structures
    metadata = MetaData()
    metadata.reflect(bind=connection)

    allocated_care_day = metadata.tables["allocated_care_day"]
    month_allocation = metadata.tables["month_allocation"]
    payment_rate = metadata.tables["payment_rate"]
    payment_request = metadata.tables["payment_request"]

    # Convert data back from string to integer using ORM
    try:
        # Update payment_request
        session.execute(
            payment_request.update()
            .values(google_sheets_child_id_temp=sa.func.cast(payment_request.c.google_sheets_child_id, sa.Integer))
            .where(payment_request.c.google_sheets_child_id.isnot(None))
        )
        session.execute(
            payment_request.update()
            .values(
                google_sheets_provider_id_temp=sa.func.cast(payment_request.c.google_sheets_provider_id, sa.Integer)
            )
            .where(payment_request.c.google_sheets_provider_id.isnot(None))
        )

        # Update payment_rate
        session.execute(
            payment_rate.update()
            .values(google_sheets_child_id_temp=sa.func.cast(payment_rate.c.google_sheets_child_id, sa.Integer))
            .where(payment_rate.c.google_sheets_child_id.isnot(None))
        )
        session.execute(
            payment_rate.update()
            .values(google_sheets_provider_id_temp=sa.func.cast(payment_rate.c.google_sheets_provider_id, sa.Integer))
            .where(payment_rate.c.google_sheets_provider_id.isnot(None))
        )

        # Update month_allocation
        session.execute(
            month_allocation.update()
            .values(google_sheets_child_id_temp=sa.func.cast(month_allocation.c.google_sheets_child_id, sa.Integer))
            .where(month_allocation.c.google_sheets_child_id.isnot(None))
        )

        # Update allocated_care_day
        session.execute(
            allocated_care_day.update()
            .values(
                provider_google_sheets_id_temp=sa.func.cast(allocated_care_day.c.provider_google_sheets_id, sa.Integer)
            )
            .where(allocated_care_day.c.provider_google_sheets_id.isnot(None))
        )

        session.commit()

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    # Drop string columns and rename temp columns back
    with op.batch_alter_table("payment_request", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_child_id")
        batch_op.drop_column("google_sheets_provider_id")
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )
        batch_op.alter_column(
            "google_sheets_provider_id_temp",
            new_column_name="google_sheets_provider_id",
            nullable=False,
        )

    with op.batch_alter_table("payment_rate", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_child_id")
        batch_op.drop_column("google_sheets_provider_id")
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )
        batch_op.alter_column(
            "google_sheets_provider_id_temp",
            new_column_name="google_sheets_provider_id",
            nullable=False,
        )

    with op.batch_alter_table("month_allocation", schema=None) as batch_op:
        batch_op.drop_column("google_sheets_child_id")
        batch_op.alter_column(
            "google_sheets_child_id_temp",
            new_column_name="google_sheets_child_id",
            nullable=False,
        )

    with op.batch_alter_table("allocated_care_day", schema=None) as batch_op:
        batch_op.drop_column("provider_google_sheets_id")
        batch_op.alter_column(
            "provider_google_sheets_id_temp",
            new_column_name="provider_google_sheets_id",
            nullable=False,
        )
