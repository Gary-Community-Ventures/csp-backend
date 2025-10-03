import zoneinfo

from flask import current_app

from app.constants import BUSINESS_TIMEZONE
from app.scripts.create_attendance import create_attendance
from app.scripts.send_attendance_emails import send_attendance_emails

from . import job_manager


@job_manager.job
def create_attendance_job(**kwargs):
    create_attendance()
    send_attendance_emails(True, True)


def schedule_attendance_job():
    cron_schedule = "0 8 * * 1"

    current_app.logger.info(f"Scheduling monthly allocation job with cron '{cron_schedule}'")

    return create_attendance_job.schedule_cron(cron_schedule)
