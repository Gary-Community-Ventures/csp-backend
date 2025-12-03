import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone

from flask import current_app

from app import create_app
from app.enums.care_day_type import CareDayType
from app.enums.email_type import EmailType
from app.models.allocated_care_day import AllocatedCareDay
from app.models.month_allocation import MonthAllocation
from app.supabase.columns import Language, ProviderType, Status
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.date_utils import get_relative_week, get_week_range
from app.utils.email.config import get_from_email_external
from app.utils.email.core import BulkEmailData, bulk_send_emails
from app.utils.email.senders import html_link
from app.utils.sms_service import BulkSmsData, bulk_send_sms


@dataclass
class MessageCopy:
    subject: str
    email: str
    sms: str


def message(name: str, lang: Language):
    domain = current_app.config.get("FRONTEND_DOMAIN")
    link = f"{domain}/family"
    if lang == Language.SPANISH:
        return MessageCopy(
            subject="Acción Requerida - Pague a su Proveedor",
            email=f"Hola {name},<br><br>Por favor recuerde iniciar sesión en el {html_link(link, 'portal')} y pagar a su proveedor por el cuidado infantil de la próxima semana. La fecha límite para enviar su pago es el lunes.",
            sms=f"No olvide pagar a su proveedor para la próxima semana. {link}",
        )

    return MessageCopy(
        subject="Action Needed - Pay Your Provider",
        email=f"Hi {name},<br><br>Please remember to log into the {html_link(link, 'portal')} and pay your provider for childcare next week. The deadline to submit your payment is Monday.",
        sms=f"Don't forget to pay your provider for next week. {link}",
    )


def provider_is_payable(provider: dict, month_allocation: MonthAllocation):
    if Provider.STATUS(provider) != Status.APPROVED:
        return False

    if Provider.TYPE(provider) == ProviderType.CENTER:
        return False

    if not Provider.PAYMENT_ENABLED(provider):
        return False

    if month_allocation.can_add_care_day():
        return True

    return False


def should_send_reminder(child: dict, week_range: tuple[date, date]):
    if Child.STATUS(child) != Status.APPROVED:
        return False
    if not Child.PAYMENT_ENABLED(child):
        return False

    week_start, week_end = week_range
    month_allocation = MonthAllocation.get_for_month(Child.ID(child), week_end)

    has_payable_provider = False
    providers = Provider.unwrap(child)
    for provider in providers:
        if provider_is_payable(provider, month_allocation):
            has_payable_provider = True

    if not has_payable_provider:
        return False

    provider_ids = [Provider.ID(p) for p in providers]
    next_week_payment = AllocatedCareDay.query.filter(
        AllocatedCareDay.provider_supabase_id.in_(provider_ids),
        AllocatedCareDay.care_month_allocation.has(child_supabase_id=Child.ID(child)),
        AllocatedCareDay.care_month_allocation.has(),
        AllocatedCareDay.date >= week_start,
        AllocatedCareDay.date <= week_end,
        AllocatedCareDay.payment_id.isnot(None),
    ).first()

    if next_week_payment is not None:
        return False

    return True


def send_payment_reminders(dry_run=False):
    family_result = (
        Family.query()
        .select(
            cols(
                Family.ID,
                Family.LANGUAGE,
                Guardian.join(
                    Guardian.EMAIL,
                    Guardian.PHONE_NUMBER,
                    Guardian.TYPE,
                    Guardian.FIRST_NAME,
                ),
                Child.join(
                    Child.ID,
                    Child.PAYMENT_ENABLED,
                    Child.STATUS,
                    Provider.join(
                        Provider.ID,
                        Provider.TYPE,
                        Provider.PAYMENT_ENABLED,
                        Provider.STATUS,
                    ),
                ),
            )
        )
        .execute()
    )
    families = unwrap_or_error(family_result)

    next_week_range = get_week_range(get_relative_week(1))

    emails: list[BulkEmailData] = []
    sms: list[BulkSmsData] = []
    for family in families:
        send_reminder = False
        children = Child.unwrap(family)
        for child in children:
            if should_send_reminder(child, next_week_range):
                send_reminder = True

        if not send_reminder:
            continue

        guardian = Guardian.get_primary_guardian(Guardian.unwrap(family))

        mes = message(Guardian.FIRST_NAME(guardian), Family.LANGUAGE(family))
        emails.append(
            BulkEmailData(
                Guardian.EMAIL(guardian),
                mes.subject,
                mes.email,
                {
                    "family_id": Family.ID(family),
                },
            )
        )
        sms.append(
            BulkSmsData(
                Guardian.PHONE_NUMBER(guardian),
                mes.sms,
                Family.LANGUAGE(family),
            )
        )

    if len(emails) == 0 and len(sms) == 0:
        current_app.logger.info("Everyone has paid there providers. No reminders to send")
        return

    if dry_run:
        current_app.logger.info(f"Would send {len(emails)} emails and {len(sms)} text messages")
        return

    batch_name = f"Payment Reminder - {datetime.now(timezone.utc).isoformat()}"
    bulk_send_emails(get_from_email_external(), emails, EmailType.PAYMENT_REMINDER, batch_name=batch_name)
    bulk_send_sms(sms)

    current_app.logger.info("payment_reminders: Finished sending attendance emails and SMS.")


if __name__ == "__main__":
    # Create Flask app context
    app = create_app()
    app.app_context().push()

    parser = argparse.ArgumentParser(description="Send attendance emails for children or providers.")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Show what would be sent without actually sending")

    args = parser.parse_args()

    send_payment_reminders(args.dry_run)
