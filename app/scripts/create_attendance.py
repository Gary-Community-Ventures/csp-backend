from dataclasses import dataclass
from datetime import date

from flask import current_app

from app import create_app
from app.enums.email_type import EmailType
from app.extensions import db
from app.models import Attendance
from app.supabase.columns import Status
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.email.config import get_from_email_external
from app.utils.email.core import BulkEmailData, bulk_send_emails
from app.utils.email.senders import html_link
from app.utils.sms_service import BulkSmsData, bulk_send_sms

# Create Flask app context
app = create_app()
app.app_context().push()


def create_child_provider_attendance(child: dict, provider: dict, last_week_date: date):
    if Child.STATUS(child) != Status.APPROVED:
        return
    if Provider.STATUS(provider) != Status.APPROVED:
        return

    return Attendance.new(Child.ID(child), Provider.ID(provider), last_week_date)


@dataclass
class MessageCopy:
    subject: str
    email: str
    sms: str


def family_message(family_name: str, link: str, lang: str):
    if lang == "es":
        return MessageCopy(
            subject="Acción necesaria - Asistencia CAP",
            email=f"<html><body>¡Hola {family_name}! Por favor, confirme las horas de atención de la semana pasada y programe la atención para la semana siguiente (si aún no lo ha hecho) antes del final del día para que su proveedor pueda recibir el pago. Haga clic {html_link(link, 'aquí')} para acceder a su portal.</body></html>",
            sms=f"¡Hola {family_name}! Por favor, confirme las horas de atención de la semana pasada y programe la atención para la semana siguiente (si aún no lo ha hecho) antes del final del día para que su proveedor pueda recibir el pago. Enlace para confirmar: {link}",
        )

    return MessageCopy(
        subject="Action Needed - CAP Attendance",
        email=f"<html><body>Hi {family_name}! Please confirm the hours of care for the past week and schedule care for the following week (if you haven’t done so already) by the end of the day, so your provider can get paid. Click {html_link(link, 'here')} to access your portal.</html></body>",
        sms=f"Hi {family_name}!  Please confirm the hours of care for the past week and schedule care for the following week (if you haven’t done so already) by the end of the day, so your provider can get paid. Link to confirm: {link}",
    )


def provider_message(provider_name: str, link: str, lang: str):
    if lang == "es":
        return MessageCopy(
            subject="Acción necesaria - Asistencia CAP",
            email=f"<html><body>Hola {provider_name}. Por favor, complete la lista de asistencia de todos los niños bajo su cuidado que reciben el subsidio de CAP antes del final del día para que puedan recibir su pago a tiempo. Haga clic {html_link(link, 'aquí')} para acceder a su portal.</body></html>",
            sms=f"Hola {provider_name}. Por favor, complete la lista de asistencia de todos los niños bajo su cuidado que reciben el subsidio de CAP antes del final del día para que puedan recibir su pago a tiempo. Enlace para confirmar: {link}",
        )

    return MessageCopy(
        subject="Action Needed - CAP Attendance",
        email=f"<html><body>Hi {provider_name}! Please fill out attendance for all children in your care who receive CAP subsidy by the end of the day, so you can get paid on time. Click {html_link(link, 'here')} to access your portal.</body></html>",
        sms=f"Hi {provider_name}! Please fill out attendance for all children in your care who receive CAP subsidy by the end of the day, so you can get paid on time. Link to confirm: {link}",
    )


def create_attendance():
    app.logger.info("create_attendance: Starting attendance creation...")

    children_result = (
        Child.query()
        .select(
            cols(
                Child.ID,
                Child.STATUS,
                Provider.join(
                    Provider.ID,
                    Provider.NAME,
                    Provider.STATUS,
                    Provider.EMAIL,
                    Provider.PHONE_NUMBER,
                    Provider.PREFERRED_LANGUAGE,
                ),
                Family.join(
                    Family.ID,
                    Family.LANGUAGE,
                    Guardian.join(
                        Guardian.FIRST_NAME,
                        Guardian.EMAIL,
                        Guardian.PHONE_NUMBER,
                        Guardian.TYPE,
                    ),
                ),
            ),
        )
        .execute()
    )
    children = unwrap_or_error(children_result)

    last_week_date = Attendance.last_week_date()

    attendances: list[Attendance] = []
    providers = {}
    families = {}
    for child in children:
        for provider in Provider.unwrap(child):
            attendance_obj = create_child_provider_attendance(child, provider, last_week_date)

            if attendance_obj is not None:
                attendances.append(attendance_obj)
                family = Family.unwrap(child)
                families[Family.ID] = family
                providers[Provider.ID] = provider

    db.session.add_all(attendances)
    db.session.commit()
    app.logger.info("create_attendance: Finished attendance creation.")

    domain = current_app.config.get("FRONTEND_DOMAIN")

    provider_link = f"{domain}/provider/attendance"

    bulk_emails: list[BulkEmailData] = []
    bulk_sms: list[BulkSmsData] = []
    for provider in providers.values():
        message_data = provider_message(Provider.NAME(provider), provider_link, Provider.PREFERRED_LANGUAGE(provider))

        bulk_emails.append(
            BulkEmailData(
                email=Provider.EMAIL(provider),
                subject=message_data.subject,
                html_content=message_data.email,
                context_data={
                    "provider_id": Provider.ID(provider),
                    "provider_name": Provider.NAME(provider),
                    "provider_language": Provider.PREFERRED_LANGUAGE(provider),
                    "recipient_type": "provider",
                    "reminder_date": last_week_date.isoformat(),
                },
            )
        )

        bulk_sms.append(
            BulkSmsData(
                phone_number="+1" + Provider.PHONE_NUMBER(provider),
                message=message_data.sms,
                lang=Provider.LANGUAGE(provider),
            )
        )

    family_link = f"{domain}/family/attendance"
    for family in families.values():
        guardian = Guardian.get_primary_guardian(Guardian.unwrap(family))
        message_data = family_message(Guardian.FIRST_NAME(guardian), family_link, Family.LANGUAGE(family))

        bulk_emails.append(
            BulkEmailData(
                email=Guardian.EMAIL(guardian),
                subject=message_data.subject,
                html_content=message_data.email,
                context_data={
                    "family_id": Family.ID(family),
                    "guardian_id": Guardian.ID(guardian),
                    "guardian_name": Guardian.FIRST_NAME(guardian),
                    "family_language": Family.LANGUAGE(family),
                    "recipient_type": "guardian",
                    "reminder_date": last_week_date.isoformat(),
                },
            )
        )

        bulk_sms.append(
            BulkSmsData(
                phone_number="+1" + Guardian.PHONE_NUMBER(guardian),
                message=message_data.sms,
                lang=Family.LANGUAGE(family),
            )
        )

    # Send emails with batch tracking
    batch_name = f"Attendance Reminder - {last_week_date}"
    bulk_send_emails(get_from_email_external(), bulk_emails, EmailType.ATTENDANCE_REMINDER, batch_name=batch_name)
    bulk_send_sms(bulk_sms)

    current_app.logger.info("create_attendance: Finished sending attendance emails and SMS.")


if __name__ == "__main__":
    create_attendance()
