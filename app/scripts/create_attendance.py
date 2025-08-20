from dataclasses import dataclass
from datetime import date

from flask import current_app

from app import create_app
from app.extensions import db
from app.models import Attendance
from app.sheets.helpers import KeyMap
from app.sheets.mappings import (
    ChildColumnNames,
    FamilyColumnNames,
    ProviderChildMappingColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_families,
    get_family,
    get_provider,
    get_provider_child_mappings,
    get_providers,
)
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


def create_child_provider_attendance(
    provider_child_mapping: KeyMap, child_rows: list[KeyMap], provider_rows: list[KeyMap], last_week_date: date
):
    child = get_child(provider_child_mapping.get(ProviderChildMappingColumnNames.CHILD_ID), child_rows)
    provider = get_provider(provider_child_mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID), provider_rows)

    if child is None:
        app.logger.warning(
            f"create_child_provider_attendance: Skipping attendance creation for child ID {provider_child_mapping.get(ProviderChildMappingColumnNames.CHILD_ID)}: Child not found in Google Sheets."
        )
        return
    if provider is None:
        app.logger.warning(
            f"create_child_provider_attendance: Skipping attendance creation for provider ID {provider_child_mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID)}: Provider not found in Google Sheets."
        )
        return

    if child.get(ChildColumnNames.STATUS).lower() != "approved":
        return
    if provider.get(ProviderColumnNames.STATUS).lower() != "approved":
        return

    return Attendance.new(child.get(ChildColumnNames.ID), provider.get(ProviderColumnNames.ID), last_week_date)


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

    child_rows = get_children()
    provider_rows = get_providers()
    provider_child_mapping_rows = get_provider_child_mappings()

    last_week_date = Attendance.last_week_date()

    attendances: list[Attendance] = []
    for provider_child_mapping in provider_child_mapping_rows:
        attendance_obj = create_child_provider_attendance(
            provider_child_mapping, child_rows, provider_rows, last_week_date
        )

        if attendance_obj is not None:
            attendances.append(attendance_obj)

    db.session.add_all(attendances)
    db.session.commit()
    app.logger.info("create_attendance: Finished attendance creation.")

    providers = set()
    families = set()
    for attendance in attendances:
        providers.add(attendance.provider_google_sheet_id)

        child = get_child(attendance.child_google_sheet_id, child_rows)
        family_id = child.get(ChildColumnNames.FAMILY_ID)
        families.add(family_id)

    domain = current_app.config.get("FRONTEND_DOMAIN")

    provider_link = f"{domain}/provider/attendance"

    bulk_emails: list[BulkEmailData] = []
    bulk_sms: list[BulkSmsData] = []
    for provider_id in providers:
        provider = get_provider(provider_id, provider_rows)

        message_data = provider_message(
            provider.get(ProviderColumnNames.NAME), provider_link, provider.get(ProviderColumnNames.LANGUAGE).lower()
        )

        bulk_emails.append(
            BulkEmailData(
                email=provider.get(ProviderColumnNames.EMAIL),
                subject=message_data.subject,
                html_content=message_data.email,
            )
        )

        bulk_sms.append(
            BulkSmsData(
                phone_number="+1" + provider.get(ProviderColumnNames.PHONE_NUMBER),
                message=message_data.sms,
                lang=provider.get(ProviderColumnNames.LANGUAGE).lower(),
            )
        )

    family_link = f"{domain}/family/attendance"

    family_rows = get_families()
    for family_id in families:
        family = get_family(family_id, family_rows)

        message_data = family_message(
            family.get(FamilyColumnNames.FIRST_NAME), family_link, family.get(FamilyColumnNames.LANGUAGE).lower()
        )

        bulk_emails.append(
            BulkEmailData(
                email=family.get(FamilyColumnNames.EMAIL),
                subject=message_data.subject,
                html_content=message_data.email,
            )
        )

        bulk_sms.append(
            BulkSmsData(
                phone_number="+1" + family.get(FamilyColumnNames.PHONE_NUMBER),
                message=message_data.sms,
                lang=family.get(FamilyColumnNames.LANGUAGE).lower(),
            )
        )

    bulk_send_emails(get_from_email_external(), bulk_emails)
    bulk_send_sms(bulk_sms)

    current_app.logger.info("create_attendance: Finished sending attendance emails and SMS.")


if __name__ == "__main__":
    create_attendance()
