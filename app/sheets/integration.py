import csv

from app.sheets.helpers import KeyMap
from app.utils.cache import Cache


def _get_sheet_data(app, sheet_name: str = "Sheet1") -> list[KeyMap]:
    """
    Retrieves data from a Google Sheet, assuming the first row contains column names.

    Args:
        spreadsheet_id: The ID of the spreadsheet to retrieve data from.
        sheet_name: The name of the sheet to retrieve data from. Defaults to "Sheet1".

    Returns:
        A list of dictionaries, where each dictionary represents a row of data.
        Returns an empty list if no data is found or on error.
    """
    spreadsheet_id = app.config.get("GOOGLE_SPREADSHEET_ID")

    if not spreadsheet_id or not app.google_sheets_service:
        app.logger.warning("Google Sheets service is not available.")
        raise ValueError("Google Sheets service is not configured.")

    result = app.google_sheets_service.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()

    values = result.get("values", [])

    if not values:
        app.logger.warning("No data found.")
        return []

    # Assume the first row contains column headers
    headers = values[0]
    data: list[KeyMap] = []
    for row in values[1:]:
        row_dict = {}
        for i, header in enumerate(headers):
            row_dict[header] = row[i] if i < len(row) else None
        data.append(KeyMap(row_dict))

    return data


def get_csv_data(csv_file: str) -> list[dict]:
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)

        data: list[KeyMap] = []
        for row in reader:
            data.append(KeyMap(row))

    return data


class SheetsManager:
    SHEETS = ["Families", "Children", "Providers", "Content", "Provider Child Mappings", "Transactions"]

    def __init__(self, app):
        self.app = app
        self._sheet_cache = Cache(self.get_all_sheet_data, expiration_time=60)

    def get_sheet_data(self, sheet_name: str = "Sheet1") -> list[KeyMap]:
        data = self._sheet_cache.get()[sheet_name]

        return data

    def get_all_sheet_data(self):
        data = {}
        for sheet in self.SHEETS:
            data[sheet] = _get_sheet_data(self.app, sheet)

        return data
