from flask import current_app

from app.scripts.create_attendance import create_attendance
from app.scripts.send_attendance_emails import send_attendance_emails

from . import job_manager


@job_manager.job
def create_attendance_job(**kwargs):
    create_attendance()


def schedule_attendance_job():
    # Run at 8:00 AM UTC on Mondays (1:00 AM MST / 2:00 AM MDT)
    cron_schedule = "0 8 * * 1"

    current_app.logger.info(f"Scheduling attendance job with cron '{cron_schedule}'")

    return create_attendance_job.schedule_cron(cron_schedule)


@job_manager.job
def send_attendance_communications_job(**kwargs):
    send_attendance_emails(True, True)


def schedule_attendance_initial_communications_job(**kwargs):
    # Run at 3:00 PM UTC on Mondays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule = "0 15 * * 1"

    current_app.logger.info(f"Scheduling attendance reminder job with cron '{cron_schedule}'")

    return send_attendance_communications_job.schedule_cron(cron_schedule)


def schedule_reminder_job():
    # Run at 3:00 PM UTC on Fridays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_first = "0 15 * * 5"
    # Run at 3:00 PM UTC on Sundays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_second = "0 15 * * 0"

    current_app.logger.info(
        f"Scheduling attendance reminder job with cron '{cron_schedule_first}' and '{cron_schedule_second}'"
    )

    return send_attendance_communications_job.schedule_cron(
        cron_schedule_first
    ), send_attendance_communications_job.schedule_cron(cron_schedule_second)
