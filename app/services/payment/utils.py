import re
from typing import Optional

STATE_NAME_TO_CODE = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


def convert_state_to_code(state: Optional[str]) -> str:
    """
    Convert a state name to its two-letter code.

    Args:
        state: State name or code

    Returns:
        Two-letter state code, or original value if already a code or not found
    """
    if not state:
        return ""

    # If it's already a 2-letter code, return as-is
    state_stripped = state.strip()
    if len(state_stripped) == 2 and state_stripped.upper() == state_stripped:
        return state_stripped

    # Try to find the state name in our mapping (case-insensitive)
    for state_name, code in STATE_NAME_TO_CODE.items():
        if state_name.lower() == state_stripped.lower():
            return code

    raise ValueError(f"Invalid state name: {state}")


def format_phone_to_e164(phone: Optional[str], default_country: str = "US") -> Optional[str]:
    """
    Format a phone number to E.164 format for Chek API.

    Args:
        phone: Phone number string in various formats
        default_country: Default country code if not provided (US = +1)

    Returns:
        Phone number in E.164 format (e.g., +13035551234) or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    # If empty after cleaning, return None
    if not digits:
        return None

    # Handle US numbers (default)
    if default_country == "US":
        # If it starts with 1 and is 11 digits, it's already formatted
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        # If it's 10 digits, add US country code
        elif len(digits) == 10:
            return f"+1{digits}"
        # If it's less than 10 digits, it's invalid
        else:
            return None

    # For other countries, you'd add their logic here
    # For now, just prepend + if not present
    return f"+{digits}" if not digits.startswith("+") else digits
