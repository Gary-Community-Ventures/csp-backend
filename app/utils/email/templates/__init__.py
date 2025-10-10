"""
Email templates package.
"""

from .attendance_reminder import AttendanceReminderTemplate
from .invitation import InvitationTemplate
from .payment_notification import PaymentNotificationTemplate

__all__ = [
    "AttendanceReminderTemplate",
    "InvitationTemplate",
    "PaymentNotificationTemplate",
]
