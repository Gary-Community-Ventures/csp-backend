import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from flask import current_app
from app.sheets.helpers import KeyMap
import csv

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheet_data(sheet_name: str = "Sheet1") -> list[dict]:
    """
    Retrieves data from a Google Sheet, assuming the first row contains column names.

    Args:
        spreadsheet_id: The ID of the spreadsheet to retrieve data from.
        sheet_name: The name of the sheet to retrieve data from. Defaults to "Sheet1".

    Returns:
        A list of dictionaries, where each dictionary represents a row of data.
        Returns an empty list if no data is found or on error.
    """
    credentials = current_app.config.get("GOOGLE_APPLICATION_CREDENTIALS")
    spreadsheet_id = current_app.config.get("GOOGLE_SPREADSHEET_ID")

    info = json.loads(credentials)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    service = build("sheets", "v4", credentials=creds)

    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get("values", [])

    if not values:
        current_app.logger.warning("No data found.")
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
