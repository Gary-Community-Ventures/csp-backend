from datetime import date

from app.models.allocated_care_day import AllocatedCareDay
from app.supabase.columns import ProviderType, Status
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Family, Guardian, Provider, Child
from app.utils.date_utils import get_relative_week


def can_make_payment(child: dict, provider: dict, week_range: tuple[date, date]):
    if Provider.TYPE(provider) == ProviderType.CENTER:
        return False

    if Child.STATUS(child) != Status.APPROVED:
        return False
    if Provider.STATUS(provider) != Status.APPROVED:
        return False

    if not Child.PAYMENT_ENABLED(child):
        return False
    if not Provider.PAYMENT_ENABLED(provider):
        return False

    week_start, week_end = week_range
    _ = AllocatedCareDay.query.filter(
        AllocatedCareDay.provider_supabase_id == Provider.ID(provider),
        AllocatedCareDay.care_month_allocation.has(child_supabase_id=Child.ID(child)),
        AllocatedCareDay.date >= week_start,
        AllocatedCareDay.date <= week_end,
        AllocatedCareDay.payment_id.isnot(None),
    ).first()


def send_payment_reminders():
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
                    Provider.join(Provider.ID, Provider.TYPE, Provider.NAME, Provider.PAYMENT_ENABLED),
                ),
            )
        )
        .execute()
    )
    families = unwrap_or_error(family_result)

    _ = get_relative_week(1)

    for family in families:
        _ = Child.unwrap(family)
        _ = Guardian.get_primary_guardian(Guardian.unwrap(family))
