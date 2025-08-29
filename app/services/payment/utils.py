import re
from typing import Optional


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
    
    # Generate random phone number for testing
    # TODO remove this in production
    import random
    phone = f"303590{random.randint(1000, 9999)}"

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
