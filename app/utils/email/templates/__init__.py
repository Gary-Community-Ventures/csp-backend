"""
Email templates package.
"""

from .attendance_reminder import AttendanceReminderTemplate
from .clerk_invitation import ClerkInvitationTemplate
from .invitation import InvitationTemplate
from .payment_notification import PaymentNotificationTemplate

__all__ = [
    "AttendanceReminderTemplate",
    "ClerkInvitationTemplate",
    "InvitationTemplate",
    "PaymentNotificationTemplate",
]
