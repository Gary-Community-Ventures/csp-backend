import argparse
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app

from app import create_app
from app.enums.email_type import EmailType
from app.models.attendance import Attendance
from app.services.payment.utils import format_phone_to_e164
from app.supabase.columns import Language, ProviderType
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.email.config import get_from_email_external
from app.utils.email.core import (
    BulkEmailData,
    bulk_send_emails,
)
from app.utils.email.templates import AttendanceReminderTemplate
from app.utils.sms_service import BulkSmsData, bulk_send_sms


@dataclass
class MessageCopy:
    subject: str
    email: str
    sms: str


class AttendanceMessages:
    class Skip(Exception):
        pass

    def __init__(self):
        self.domain = current_app.config.get("FRONTEND_DOMAIN")

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
                            Guardian.ID,
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
        if child is None:
            raise self.Skip

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
            phone_number=format_phone_to_e164(Guardian.PHONE_NUMBER(guardian)),
            message=message_data.sms,
            lang=lang,
        )

        return Family.ID(family), email, sms

    def _family_message(self, family_name: str, lang: str):
        link = f"{self.domain}/family/attendance"
        language = Language.SPANISH if lang == "es" else Language.ENGLISH
        email_html = AttendanceReminderTemplate.get_family_content(family_name, link, language)

        if lang == "es":
            return MessageCopy(
                subject="Acción necesaria - Asistencia CAP",
                email=email_html,
                sms=f"Confirme los días de cuidado de la semana pasada para que su proveedor pueda recibir su pago. {link}",
            )

        return MessageCopy(
            subject="Action Needed - CAP Attendance",
            email=email_html,
            sms=f"Confirm your days of care for the past week so your provider can get paid. {link}",
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
                    Provider.PREFERRED_LANGUAGE,
                    Provider.TYPE,
                )
            )
            .execute()
        )
        return unwrap_or_error(provider_result)

    def _message(self, record: Attendance, data):
        provider = Provider.find_by_id(data, record.provider_supabase_id)
        if provider is None:
            raise self.Skip

        lang = Provider.PREFERRED_LANGUAGE(provider)

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
            phone_number=format_phone_to_e164(Provider.PHONE_NUMBER(provider)),
            message=message_data.sms,
            lang=lang,
        )

        return Provider.ID(provider), email, sms

    def _provider_message(self, provider_name: str, lang: str):
        link = f"{self.domain}/provider/attendance"
        language = Language.SPANISH if lang == "es" else Language.ENGLISH
        email_html = AttendanceReminderTemplate.get_provider_content(provider_name, link, language)

        if lang == "es":
            return MessageCopy(
                subject="Acción necesaria - Asistencia CAP",
                email=email_html,
                sms=f"Confirme la asistencia de todos los niños bajo su cuidado que reciben el subsidio CAP, para que pueda recibir su pago a tiempo. {link}",
            )

        return MessageCopy(
            subject="Action Needed - CAP Attendance",
            email=email_html,
            sms=f"Please confirm attendance for all children in your care who receive so you can get paid on time. {link}",
        )

    def _center_message(self, provider_name: str, lang: str):
        link = f"{self.domain}/provider/attendance"
        language = Language.SPANISH if lang == "es" else Language.ENGLISH
        email_html = AttendanceReminderTemplate.get_center_content(provider_name, link, language)

        if lang == "es":
            return MessageCopy(
                subject="Acción necesaria - Asistencia CAP",
                email=email_html,
                sms=f"Por favor, complete la asistencia de todos los niños bajo su cuidado que reciben subsidio de CAP del mes pasado antes del fin de semana. Si ya envió la verificación de asistencia del mes pasado, ignore este correo electrónico. {link}",
            )

        return MessageCopy(
            subject="Action Needed - CAP Attendance",
            email=email_html,
            sms=f"Please fill out attendance for all children in your care who receive CAP subsidy for the past month by the end of the week. If you have already submitted last month's attendance verification, please disregard this email. {link}",
        )


def send_attendance_communications(send_to_families=False, send_to_providers=False, dry_run=False):
    current_app.logger.info("create_attendance: Starting attendance creation...")
    bulk_emails: list[BulkEmailData] = []
    bulk_text_messages: list[BulkSmsData] = []

    if not send_to_families and not send_to_providers:
        current_app.logger.info("create_attendance: No recipients specified. Exiting.")
        return

    if send_to_families:
        current_app.logger.info("create_attendance: Gathering family emails and SMS...")
        family_messages = FamilyAttendanceMessages()
        emails, text_messages = family_messages.send_messages()
        bulk_emails.extend(emails)
        bulk_text_messages.extend(text_messages)

    if send_to_providers:
        current_app.logger.info("create_attendance: Gathering provider emails and SMS...")
        provider_messages = ProviderAttendanceMessages()
        emails, text_messages = provider_messages.send_messages()
        bulk_emails.extend(emails)
        bulk_text_messages.extend(text_messages)

    if dry_run:
        current_app.logger.info(f"Would send {len(bulk_emails)} emails and {len(bulk_text_messages)} text messages")
        return

    batch_name = f"Attendance Reminder - {datetime.now(timezone.utc).isoformat()}"
    bulk_send_emails(get_from_email_external(), bulk_emails, EmailType.ATTENDANCE_REMINDER, batch_name=batch_name)
    bulk_send_sms(bulk_text_messages)

    current_app.logger.info("attendance_communications: Finished sending attendance emails and SMS.")


if __name__ == "__main__":
    # Create Flask app context
    app = create_app()
    app.app_context().push()

    parser = argparse.ArgumentParser(description="Send attendance emails for children or providers.")
    parser.add_argument("-f", "--family", action="store_true", help="Send attendance emails to families")
    parser.add_argument("-p", "--provider", action="store_true", help="Send attendance emails to providers")
    parser.add_argument("-a", "--all", action="store_true", help="Send attendance emails to all children and providers")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Show what would be sent without actually sending")

    args = parser.parse_args()

    send_attendance_communications(args.family or args.all, args.provider or args.all, args.dry_run)
