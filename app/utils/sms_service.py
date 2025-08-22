from dataclasses import dataclass

from flask import current_app
from twilio.rest import Client


def create_message(message: str, lang: str):
    environment = current_app.config.get("FLASK_ENV", "development")

    # Add environment prefix to subject for non-production environments
    if environment != "production":
        message = f"[{environment.upper()}] {message}"

    if lang == "es":
        message += " Se pueden aplicar tarifas de mensajes y datos. Responda STOP para cancelar"
    else:
        message += " Msg&data rates may apply. Reply STOP to cancel"

    return message


def send_sms(phone_number: str, message: str, lang: str):
    account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_PHONE_NUMBER")
    client = Client(account_sid, auth_token)

    message = create_message(message, lang)

    try:
        message = client.messages.create(
            from_=from_number,
            body=message,
            to=phone_number,
        )
        current_app.logger.info(f"SMS sent to {phone_number}")
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending SMS: {e}")
        return False


@dataclass
class BulkSmsData:
    phone_number: str
    message: str
    lang: str


def bulk_send_sms(data: list[BulkSmsData]):
    all_successful = True
    for sms_data in data:
        success = send_sms(sms_data.phone_number, sms_data.message, sms_data.lang)

        if not success:
            all_successful = False

    return all_successful
