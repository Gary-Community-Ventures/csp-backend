from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Family, Guardian, Provider, Child


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
                    Provider.join(Provider.ID, Provider.TYPE, Provider.NAME),
                ),
            )
        )
        .execute()
    )
    families = unwrap_or_error(family_result)

    for family in families:
        guardian = Guardian.get_primary_guardian(Guardian.unwrap(family))
