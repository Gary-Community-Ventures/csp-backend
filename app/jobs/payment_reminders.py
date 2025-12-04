from flask import current_app

from app.scripts.send_payment_reminders import send_payment_reminders

from . import job_manager


@job_manager.job
def send_payment_reminders_job(**kwargs):
    send_payment_reminders()


def schedule_payment_reminders_job():
    # Run at 3:00 PM UTC on Fridays (8:00 AM MST / 9:00 AM MDT)
    cron_schedule = "0 15 * * 5"

    current_app.logger.info(f"Scheduling payment reminders job with cron '{cron_schedule}'")

    return send_payment_reminders_job.schedule_cron(cron_schedule)
