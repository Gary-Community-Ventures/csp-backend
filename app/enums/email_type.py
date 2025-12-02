from enum import Enum


class EmailType(str, Enum):
    # System types
    RESEND = "resend"

    # Payment-related
    CARE_DAYS_PAYMENT = "care_days_payment"
    LUMP_SUM_PAYMENT = "lump_sum_payment"
    PAYMENT_NOTIFICATION = "payment_notification"
    PAYMENT_RATE_CREATED = "payment_rate_created"

    # Invitation system
    INVITE_REMINDER = "invite_reminder"
    PROVIDER_INVITED = "provider_invited"
    PROVIDER_INVITE_ACCEPTED = "provider_invite_accepted"
    FAMILY_INVITED = "family_invited"
    FAMILY_INVITE_ACCEPTED = "family_invite_accepted"
    PROVIDER_FAMILY_INVITATION = "provider_family_invitation"
    FAMILY_PROVIDER_INVITATION = "family_provider_invitation"

    # Reminders
    ATTENDANCE_REMINDER = "attendance_reminder"
