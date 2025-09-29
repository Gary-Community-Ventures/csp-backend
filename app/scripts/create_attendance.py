import argparse
from datetime import date

from app import create_app
from app.extensions import db
from app.models import Attendance
from app.models.allocated_care_day import AllocatedCareDay
from app.supabase.columns import ProviderType, Status
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Provider
from app.utils.date_utils import get_week_range

# Create Flask app context
app = create_app()
app.app_context().push()


def create_child_provider_attendance(
    child: dict, provider: dict, last_week_date: date, last_week_range: tuple[date, date]
):
    if Child.STATUS(child) != Status.APPROVED:
        return
    if Provider.STATUS(provider) != Status.APPROVED:
        return

    if not Child.PAYMENT_ENABLED(child):
        return
    if not Provider.PAYMENT_ENABLED(provider):
        return

    if Provider.TYPE(provider) != ProviderType.CENTER:
        # NOTE: don't create attendance for providers that are not scheduled
        week_start, week_end = last_week_range
        payed_care_day = AllocatedCareDay.query.filter(
            AllocatedCareDay.provider_supabase_id == Provider.ID(provider),
            AllocatedCareDay.child_supabase_id == Child.ID(child),
            AllocatedCareDay.date >= week_start,
            AllocatedCareDay.date <= week_end,
            AllocatedCareDay.payment_id.isnot(None),
        ).first()

        if payed_care_day is None:
            return

    return Attendance.new(Child.ID(child), Provider.ID(provider), last_week_date)


def create_attendance(dry_run=False):
    app.logger.info("create_attendance: Starting attendance creation...")

    children_result = (
        Child.query()
        .select(
            cols(
                Child.ID,
                Child.STATUS,
                Child.PAYMENT_ENABLED,
                Provider.join(
                    Provider.ID,
                    Provider.STATUS,
                    Provider.PAYMENT_ENABLED,
                    Provider.TYPE,
                ),
                Family.join(
                    Family.ID,
                ),
            ),
        )
        .execute()
    )
    children = unwrap_or_error(children_result)

    last_week_date = Attendance.last_week_date()
    last_week_range = get_week_range(last_week_date)

    attendances: list[Attendance] = []
    for child in children:
        for provider in Provider.unwrap(child):
            attendance_obj = create_child_provider_attendance(child, provider, last_week_date, last_week_range)

            if dry_run and attendance_obj is not None:
                app.logger.info(f"Created: {attendance_obj}")

            if attendance_obj is not None:
                attendances.append(attendance_obj)

    if dry_run:
        app.logger.info(f"Would create {len(attendances)} attendance records")
        return

    db.session.add_all(attendances)
    db.session.commit()
    app.logger.info("create_attendance: Finished attendance creation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create attendance records for a given child provider pairs.")
    parser.add_argument(
        "-d", "--dry-run", action="store_true", help="Show what would be created without actually creating"
    )

    args = parser.parse_args()

    create_attendance(args.dry_run)
