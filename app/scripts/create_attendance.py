from datetime import date

from app import create_app
from app.extensions import db
from app.models import Attendance
from app.sheets.helpers import KeyMap
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderChildMappingColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_provider,
    get_provider_child_mappings,
    get_providers,
)

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

    # TODO: send emails


if __name__ == "__main__":
    create_attendance()
