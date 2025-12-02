import argparse
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app

from app import create_app
from app.enums.email_type import EmailType
from app.models.provider_invitation import ProviderInvitation
from app.services.payment.utils import format_phone_to_e164
from app.supabase.columns import Language
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.email.config import get_from_email_external
from app.utils.email.core import BulkEmailData, bulk_send_emails
from app.utils.email.senders import html_link
from app.utils.sms_service import BulkSmsData, bulk_send_sms


@dataclass
class MessageCopy:
    subject: str
    email: str
    sms: str


def message(family_name: str, default_child_id: str, language: Language):
    domain = current_app.config.get("FRONTEND_DOMAIN")
    link = f"{domain}/family/{default_child_id}/providers/invite"

    if language == Language.SPANISH:
        portal_link = html_link(link, "portal")
        return MessageCopy(
            subject="Acción necesaria - Invitación de proveedor CAP",
            email=f"Hola {family_name}:<br><br>Nuestros registros indican que aún no ha referido a su proveedor desde su {portal_link}, por lo que no podrá programar atención ni pagarle.<br><br>Inicie sesión en su {portal_link} e invite a su proveedor a solicitar su cita. Le recordamos que los proveedores deben solicitar su cita dentro de las 2 semanas posteriores a su aprobación.<br><br>Si tiene alguna pregunta, no dude en contactarnos.<br><br>¡Gracias!<br>El equipo de CAP",
            sms=f"Hola {family_name}, nuestros registros indican que aún no ha referido a su proveedor. Inicie sesión en su portal e invite a su proveedor a solicitar su cita. {link}",
        )

    portal_link = html_link(link, "portal")
    return MessageCopy(
        subject="Action Needed - CAP Provider Invitation",
        email=f"Hello {family_name},<br><br>Our records indicate you have not referred your provider from your {portal_link} yet, so you won't be able to schedule care or pay your provider.<br><br>Please log into your {portal_link} and invite your provider to apply. As a reminder, providers must apply within 2 weeks of your approval.<br><br>Please let us know if you have any questions.<br><br>Thanks!<br>The CAP Team",
        sms=f"Hello {family_name}, our records indicate you have not referred your provider yet. Please log into your portal and invite your provider to apply. {link}",
    )


def send_invite_reminders(dry_run=False):
    family_result = (
        Family.query()
        .select(
            cols(
                Family.ID,
                Family.LINK_ID,
                Family.LANGUAGE,
                Guardian.join(
                    Guardian.EMAIL,
                    Guardian.PHONE_NUMBER,
                    Guardian.TYPE,
                    Guardian.FIRST_NAME,
                ),
                Child.join(
                    Child.ID,
                    Provider.join(Provider.ID),
                ),
            )
        )
        .execute()
    )
    families = unwrap_or_error(family_result)

    emails: list[BulkEmailData] = []
    sms: list[BulkSmsData] = []
    for family in families:
        if Family.LINK_ID(family):
            continue

        has_provider = False
        for child in Child.unwrap(family):
            if len(Provider.unwrap(child)) != 0:
                has_provider = True
                break

        if has_provider:
            continue

        child_ids = [Child.ID(c) for c in Child.unwrap(family)]
        if ProviderInvitation.invitations_by_child_ids(child_ids).count() != 0:
            continue

        guardian = Guardian.get_primary_guardian(Guardian.unwrap(family))

        message_data = message(Guardian.FIRST_NAME(guardian), child_ids[0], Family.LANGUAGE(family))
        emails.append(
            BulkEmailData(
                email=Guardian.EMAIL(guardian),
                subject=message_data.subject,
                html_content=message_data.email,
                context_data={
                    "family_id": Family.ID(family),
                },
            )
        )
        sms.append(
            BulkSmsData(
                phone_number=format_phone_to_e164(Guardian.PHONE_NUMBER(guardian)),
                message=message_data.sms,
                lang=Family.LANGUAGE(family),
            )
        )

    if len(emails) == 0 or len(sms) == 0:
        current_app.logger.info(f"No emails or SMS messages to send")
        return

    if dry_run:
        current_app.logger.info(f"Would send {len(emails)} emails and {len(sms)} SMS messages")
        return

    batch_name = f"Invite Reminders - {datetime.now(timezone.utc).isoformat()}"
    bulk_send_emails(get_from_email_external(), emails, EmailType.INVITE_REMINDER, batch_name=batch_name)
    bulk_send_sms(sms)

    current_app.logger.info("invite_reminder: Finished sending invite reminder emails and SMS.")


if __name__ == "__main__":
    app = create_app()
    app.app_context().push()

    parser = argparse.ArgumentParser(description="Send attendance emails for children or providers.")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Show what would be sent without actually sending")

    args = parser.parse_args()

    send_invite_reminders(dry_run=args.dry_run)
