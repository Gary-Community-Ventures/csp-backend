from flask import current_app

from app.scripts.create_attendance import create_attendance
from app.scripts.send_attendance_communications import send_attendance_communications

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
    send_attendance_communications(True, True)


def schedule_attendance_communications_job():
    # Run at 3:00 PM UTC on Mondays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_initial = "0 15 * * 1"
    # Run at 3:00 PM UTC on Fridays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_first_reminder = "0 15 * * 5"
    # Run at 3:00 PM UTC on Sundays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_second_reminder = "0 15 * * 0"

    current_app.logger.info(
        f"Scheduling attendance communications job with crons '{cron_schedule_initial}'(initial), "
        f"'{cron_schedule_first_reminder}'(first reminder), and '{cron_schedule_second_reminder}'(second reminder)"
    )

    return (
        send_attendance_communications_job.schedule_cron(cron_schedule_initial),
        send_attendance_communications_job.schedule_cron(cron_schedule_first_reminder),
        send_attendance_communications_job.schedule_cron(cron_schedule_second_reminder),
    )
