from markupsafe import Markup

from app.admin.views import SecureModelView


class PaymentAdminView(SecureModelView):
    """Custom admin view for Payment model"""

    # Display settings
    column_list = [
        "id",
        "external_provider_id",
        "external_child_id",
        "amount_cents",
        "payment_method",
        "status",
        "chek_transfer_id",
        "chek_ach_payment_id",
        "successful_attempt",
        "created_at",
    ]

    column_searchable_list = [
        "external_provider_id",
        "external_child_id",
    ]

    column_filters = ["payment_method", "external_provider_id", "external_child_id", "created_at"]

    column_sortable_list = [
        "id",
        "amount_cents",
        "payment_method",
        "created_at",
        "external_provider_id",
        "external_child_id",
    ]

    # Format columns
    column_formatters = {
        "amount_cents": lambda v, c, m, p: f"${m.amount_cents / 100:.2f}" if m.amount_cents else "$0.00",
        "successful_attempt": lambda v, c, m, p: (
            Markup(
                f'<a href="/admin/paymentattempt/details/?id={m.successful_attempt_id}">'
                f"{m.successful_attempt_id}</a>"
            )
            if m.successful_attempt_id
            else None
        ),
        "chek_transfer_id": lambda v, c, m, p: m.chek_transfer_id or "-",
        "chek_ach_payment_id": lambda v, c, m, p: m.chek_ach_payment_id or "-",
    }

    column_labels = {
        "external_provider_id": "Provider ID",
        "external_child_id": "Child ID",
        "amount_cents": "Amount",
        "payment_method": "Method",
        "chek_transfer_id": "Chek Transfer",
        "chek_ach_payment_id": "ACH Payment",
        "successful_attempt": "Successful Attempt",
        "created_at": "Created",
    }

    # Details view
    column_details_list = [
        "id",
        "payment_intent_id",
        "successful_attempt_id",
        "external_provider_id",
        "external_child_id",
        "amount_cents",
        "payment_method",
        "status",
        "chek_transfer_id",
        "chek_ach_payment_id",
        "family_chek_user_id",
        "provider_chek_user_id",
        "provider_chek_direct_pay_id",
        "provider_chek_card_id",
        "provider_payment_settings_id",
        "month_allocation_id",
        "created_at",
        "updated_at",
    ]

    # Note: Links to related models are handled via column_formatters above


class PaymentAttemptAdminView(SecureModelView):
    """Custom admin view for PaymentAttempt model"""

    # Display settings
    column_list = [
        "id",
        "payment_intent_id",
        "payment_id",
        "attempt_number",
        "payment_method",
        "status",
        "family_chek_user_id",
        "provider_chek_user_id",
        "provider_chek_card_id",
        "provider_chek_direct_pay_id",
        "wallet_transfer_id",
        "ach_payment_id",
        "error_message",
        "created_at",
    ]

    column_searchable_list = [
        "wallet_transfer_id",
        "ach_payment_id",
        "family_chek_user_id",
        "provider_chek_user_id",
        "error_message",
    ]

    column_filters = ["payment_method", "attempt_number", "created_at", "wallet_transfer_at", "ach_payment_at"]

    column_sortable_list = ["id", "attempt_number", "payment_method", "created_at"]

    # Format columns
    column_formatters = {
        "payment_id": lambda v, c, m, p: (
            Markup(f'<a href="/admin/payment/details/?id={m.payment_id}">{m.payment_id}</a>') if m.payment_id else "-"
        ),
        "payment_intent_id": lambda v, c, m, p: (
            Markup(f'<a href="/admin/paymentintent/details/?id={m.payment_intent_id}">{m.payment_intent_id}</a>')
            if m.payment_intent_id
            else None
        ),
        "status": lambda v, c, m, p: Markup(
            f'<span class="label label-{PaymentAttemptAdminView._status_class(m.status)}">{m.status}</span>'
        ),
        "error_message": lambda v, c, m, p: (
            Markup(f'<span title="{m.error_message}">{m.error_message[:50]}...</span>')
            if m.error_message and len(m.error_message) > 50
            else m.error_message
        ),
    }

    column_labels = {
        "payment_intent_id": "Intent",
        "payment_id": "Payment",
        "attempt_number": "#",
        "payment_method": "Method",
        "family_chek_user_id": "Family Chek User",
        "provider_chek_user_id": "Provider Chek User",
        "provider_chek_card_id": "Provider Card ID",
        "provider_chek_direct_pay_id": "Provider DirectPay ID",
        "wallet_transfer_id": "Transfer ID",
        "ach_payment_id": "ACH ID",
        "error_message": "Error",
        "created_at": "Created",
    }

    # Details view
    column_details_list = [
        "id",
        "payment_intent_id",
        "payment_id",
        "attempt_number",
        "payment_method",
        "status",
        "chek_user_id",
        "chek_card_id",
        "chek_direct_pay_id",
        "wallet_transfer_id",
        "wallet_transfer_at",
        "ach_payment_id",
        "ach_payment_at",
        "error_message",
        "is_successful",
        "is_failed",
        "is_processing",
        "created_at",
        "updated_at",
    ]

    @staticmethod
    def _status_class(status):
        """Return Bootstrap label class based on status"""
        status_map = {
            "success": "success",
            "successful": "success",
            "failed": "danger",
            "pending": "warning",
            "processing": "info",
            "wallet_funded": "info",
        }
        return status_map.get(status, "default")


class PaymentIntentAdminView(SecureModelView):
    """Custom admin view for PaymentIntent model"""

    # Display settings
    column_list = [
        "id",
        "provider_external_id",
        "child_external_id",
        "amount_cents",
        "status",
        "payment",
        "attempts_count",
        "created_at",
    ]

    column_searchable_list = [
        "provider_external_id",
        "child_external_id",
    ]

    column_filters = ["provider_external_id", "child_external_id", "created_at"]

    column_sortable_list = ["id", "amount_cents", "created_at", "provider_external_id", "child_external_id"]

    # Format columns
    column_formatters = {
        "amount_cents": lambda v, c, m, p: f"${m.amount_cents / 100:.2f}" if m.amount_cents else "$0.00",
        "payment": lambda v, c, m, p: (
            Markup(f'<a href="/admin/payment/details/?id={m.payment.id}">View Payment</a>') if m.payment else "-"
        ),
        "attempts_count": lambda v, c, m, p: len(m.attempts) if m.attempts else 0,
        "status": lambda v, c, m, p: Markup(
            f'<span class="label label-{PaymentIntentAdminView._status_class(m.status)}">{m.status}</span>'
        ),
    }

    column_labels = {
        "provider_external_id": "Provider ID",
        "child_external_id": "Child ID",
        "amount_cents": "Amount",
        "attempts_count": "# Attempts",
        "created_at": "Created",
    }

    @staticmethod
    def _status_class(status):
        """Return Bootstrap label class based on status"""
        status_map = {"paid": "success", "failed": "danger", "pending": "warning", "processing": "info"}
        return status_map.get(status, "default")
