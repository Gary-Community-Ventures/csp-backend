from flask import current_app

from app.scripts.send_invite_reminders import send_invite_reminders

from . import job_manager


@job_manager.job
def send_invite_reminders_job(**kwargs):
    send_invite_reminders()


def schedule_invite_reminders_job():
    # Run at 3:00 PM UTC on Tuesdays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_tuesday = "0 15 * * 2"
    # Run at 3:00 PM UTC on Fridays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule_friday = "0 15 * * 5"

    current_app.logger.info(
        f"Scheduling invite reminders job with crons '{cron_schedule_tuesday}' (Tuesday) and "
        f"'{cron_schedule_friday}' (Friday)"
    )

    return (
        send_invite_reminders_job.schedule_cron(cron_schedule_tuesday),
        send_invite_reminders_job.schedule_cron(cron_schedule_friday),
    )
