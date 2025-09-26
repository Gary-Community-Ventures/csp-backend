import argparse
from dataclasses import dataclass

from app import create_app
from app.models.attendance import Attendance
from app.supabase.columns import ProviderType
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.email_service import (
    BulkEmailData,
    bulk_send_emails,
    get_from_email_external,
    html_link,
)
from app.utils.sms_service import BulkSmsData, bulk_send_sms

# Create Flask app context
app = create_app()
app.app_context().push()


@dataclass
class MessageCopy:
    subject: str
    email: str
    sms: str


class AttendanceMessages:
    domain = app.config.get("FRONTEND_DOMAIN")

    class Skip(Exception):
        pass

    def _get_records(self):
        raise NotImplementedError()

    def _get_data(self):
        raise NotImplementedError()

    def _message(self, record, data) -> tuple[str, BulkEmailData, BulkSmsData]:
        raise NotImplementedError()

    def send_messages(self) -> tuple[list[BulkEmailData], list[BulkSmsData]]:
        records = self._get_records()
        data = self._get_data()

        emails: dict[str, BulkEmailData] = {}
        text_messages: dict[str, BulkSmsData] = {}
        for record in records:
            try:
                id, email, text_message = self._message(record, data)
            except self.Skip:
                continue
            emails[id] = email
            text_messages[id] = text_message

        emails_to_send = list(emails.values())
        text_messages_to_send = list(text_messages.values())

        # TODO: update this copy when we have it.
        todo_message = "TODO: UPDATE COPY. DON'T FORGET TO UPDATE THESE MESSAGES: "  # FIXME: remove
        emails_to_send = [  # FIXME: remove
            BulkEmailData(email.email, todo_message + email.subject, todo_message + email.html_content)  # FIXME: remove
            for email in emails_to_send  # FIXME: remove
        ]  # FIXME: remove
        text_messages_to_send = [  # FIXME: remove
            BulkSmsData(
                text_message.phone_number, todo_message + text_message.message, text_message.lang
            )  # FIXME: remove
            for text_message in text_messages_to_send  # FIXME: remove
        ]  # FIXME: remove

        return emails_to_send, text_messages_to_send


class FamilyAttendanceMessages(AttendanceMessages):
    def _get_records(self):
        return Attendance.filter_by_due_family_attendance().all()

    def _get_data(self):
        children_result = (
            Child.query()
            .select(
                cols(
                    Child.ID,
                    Family.join(
                        Family.ID,
                        Family.LANGUAGE,
                        Guardian.join(
                            Guardian.EMAIL,
                            Guardian.PHONE_NUMBER,
                            Guardian.TYPE,
                            Guardian.FIRST_NAME,
                        ),
                    ),
                )
            )
            .execute()
        )
        return unwrap_or_error(children_result)

    def _message(self, record: Attendance, data):
        child = Child.find_by_id(data, record.child_supabase_id)
        family = Family.unwrap(child)
        guardian = Guardian.get_primary_guardian(Guardian.unwrap(family))
        lang = Family.LANGUAGE(family)

        message_data = self._family_message(Guardian.FIRST_NAME(guardian), lang)

        email = BulkEmailData(
            email=Guardian.EMAIL(guardian),
            subject=message_data.subject,
            html_content=message_data.email,
            context_data={
                "family_id": Family.ID(family),
                "child_id": Child.ID(child),
                "guardian_id": Guardian.ID(guardian),
                "guardian_name": Guardian.FIRST_NAME(guardian),
                "family_language": lang,
                "recipient_type": "guardian",
                "reminder_date": record.week.isoformat(),
            },
        )
        sms = BulkSmsData(
            phone_number="+1" + Guardian.PHONE_NUMBER(guardian),
            message=message_data.sms,
            lang=lang,
        )

        return Family.ID(family), email, sms

    def _family_message(self, family_name: str, lang: str):
        link = f"{self.domain}/family/attendance"
        if lang == "es":
            return MessageCopy(
                subject="Acción necesaria - Asistencia CAP",
                email=f"<html><body>¡Hola {family_name}! Por favor, confirme los días de atención de la semana pasada y programe la atención para la semana siguiente (si aún no lo ha hecho) antes del final del día para que su proveedor pueda recibir el pago. Haga clic {html_link(link , 'aquí')} para acceder a su portal.</body></html>",
                sms=f"¡Hola {family_name}! Por favor, confirme los días de atención de la semana pasada y programe la atención para la semana siguiente (si aún no lo ha hecho) antes del final del día para que su proveedor pueda recibir el pago. Enlace para confirmar: {link}",
            )

        return MessageCopy(
            subject="Action Needed - CAP Attendance",
            email=f"<html><body>Hi {family_name}! Please confirm the days of care for the past week and schedule care for the following week (if you haven't done so already) by the end of the day, so your provider can get paid. Click {html_link(link, 'here')} to access your portal.</html></body>",
            sms=f"Hi {family_name}!  Please confirm the days of care for the past week and schedule care for the following week (if you haven't done so already) by the end of the day, so your provider can get paid. Link to confirm: {link}",
        )


class ProviderAttendanceMessages(AttendanceMessages):
    def _get_records(self):
        return Attendance.filter_by_due_provider_attendance().all()

    def _get_data(self):
        provider_result = (
            Provider.query()
            .select(
                cols(
                    Provider.ID,
                    Provider.NAME,
                    Provider.EMAIL,
                    Provider.PHONE_NUMBER,
                    Provider.LANGUAGE,
                    Provider.TYPE,
                )
            )
            .execute()
        )
        return unwrap_or_error(provider_result)

    def _message(self, record: Attendance, data):
        provider = Provider.find_by_id(data, record.provider_supabase_id)
        lang = Provider.LANGUAGE(provider)

        if Provider.TYPE(provider) == ProviderType.CENTER and not record.center_is_due():
            raise self.Skip

        if Provider.TYPE(provider) == ProviderType.CENTER:
            message_data = self._center_message(Provider.NAME(provider), lang)
        else:
            message_data = self._provider_message(Provider.NAME(provider), lang)

        email = BulkEmailData(
            email=Provider.EMAIL(provider),
            subject=message_data.subject,
            html_content=message_data.email,
            context_data={
                "provider_id": Provider.ID(provider),
                "provider_name": Provider.NAME(provider),
                "provider_language": lang,
                "provider_type": Provider.TYPE(provider),
                "recipient_type": "provider",
                "reminder_date": record.week.isoformat(),
            },
        )
        sms = BulkSmsData(
            phone_number="+1" + Provider.PHONE_NUMBER(provider),
            message=message_data.sms,
            lang=lang,
        )

        return Provider.ID(provider), email, sms

    def _provider_message(self, provider_name: str, lang: str):
        link = f"{self.domain}/provider/attendance"

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

    def _center_message(self, provider_name: str, lang: str):
        link = f"{self.domain}/provider/attendance"
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


def send_attendance_emails(send_to_families=False, send_to_providers=False, dry_run=False):
    app.logger.info("create_attendance: Starting attendance creation...")
    bulk_emails: list[BulkEmailData] = []
    bulk_text_messages: list[BulkSmsData] = []

    if not send_to_families and not send_to_providers:
        app.logger.info("create_attendance: No recipients specified. Exiting.")
        return

    if send_to_families:
        app.logger.info("create_attendance: Gathering family emails and SMS...")
        family_messages = FamilyAttendanceMessages()
        emails, text_messages = family_messages.send_messages()
        bulk_emails.extend(emails)
        bulk_text_messages.extend(text_messages)

    if send_to_providers:
        app.logger.info("create_attendance: Gathering provider emails and SMS...")
        provider_messages = ProviderAttendanceMessages()
        emails, text_messages = provider_messages.send_messages()
        bulk_emails.extend(emails)
        bulk_text_messages.extend(text_messages)

    if dry_run:
        app.logger.info(f"Would send {len(bulk_emails)} emails and {len(bulk_text_messages)} text messages")
        return

    bulk_send_emails(get_from_email_external(), bulk_emails)
    bulk_send_sms(bulk_text_messages)

    app.logger.info("create_attendance: Finished sending attendance emails and SMS.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send attendance emails for children or providers.")
    parser.add_argument("-f", "--family", action="store_true", help="Send attendance emails to families")
    parser.add_argument("-p", "--provider", action="store_true", help="Send attendance emails to providers")
    parser.add_argument("-a", "--all", action="store_true", help="Send attendance emails to all children and providers")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Show what would be sent without actually sending")

    args = parser.parse_args()

    send_attendance_emails(args.family or args.all, args.provider or args.all, args.dry_run)
