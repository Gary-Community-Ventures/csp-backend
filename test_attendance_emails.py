"""
Test script for attendance emails.
Run with: flask shell < test_attendance_emails.py
Or copy/paste into flask shell.
"""

from app.enums.email_type import EmailType
from app.supabase.columns import Language
from app.utils.email.config import get_from_email_external
from app.utils.email.core import send_email
from app.utils.email.templates import AttendanceReminderTemplate

# Test Family Attendance Email (English)
print("Sending family attendance email (English)...")
email_html = AttendanceReminderTemplate.get_family_content(
    "John", "http://localhost:5173/family/attendance", Language.ENGLISH
)
send_email(
    from_email=get_from_email_external(),
    to_emails=["tlillis@garycommunity.org"],
    subject="Test: Action Needed - CAP Attendance",
    html_content=email_html,
    email_type=EmailType.ATTENDANCE_REMINDER,
    context_data={"test": True},
)

# Test Provider Attendance Email (English)
print("Sending provider attendance email (English)...")
email_html = AttendanceReminderTemplate.get_provider_content(
    "Provider Name", "http://localhost:5173/provider/attendance", Language.ENGLISH
)
send_email(
    from_email=get_from_email_external(),
    to_emails=["tlillis@garycommunity.org"],
    subject="Test: Action Needed - CAP Attendance",
    html_content=email_html,
    email_type=EmailType.ATTENDANCE_REMINDER,
    context_data={"test": True},
)

# Test Family Attendance Email (Spanish)
print("Sending family attendance email (Spanish)...")
email_html = AttendanceReminderTemplate.get_family_content(
    "María", "http://localhost:5173/family/attendance", Language.SPANISH
)
send_email(
    from_email=get_from_email_external(),
    to_emails=["tlillis@garycommunity.org"],
    subject="Test: Acción necesaria - Asistencia CAP",
    html_content=email_html,
    email_type=EmailType.ATTENDANCE_REMINDER,
    context_data={"test": True},
)

# Test Center Attendance Email (English)
print("Sending center attendance email (English)...")
email_html = AttendanceReminderTemplate.get_center_content(
    "ABC Daycare Center", "http://localhost:5173/provider/attendance", Language.ENGLISH
)
send_email(
    from_email=get_from_email_external(),
    to_emails=["tlillis@garycommunity.org"],
    subject="Test: Action Needed - CAP Attendance",
    html_content=email_html,
    email_type=EmailType.ATTENDANCE_REMINDER,
    context_data={"test": True},
)

print("All test emails sent!")
