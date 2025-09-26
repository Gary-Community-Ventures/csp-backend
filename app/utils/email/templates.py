"""
Email templates with multi-language support.
"""

from typing import Dict

from app.enums.payment_method import PaymentMethod
from app.supabase.columns import Language


class PaymentNotificationTemplate:
    """Payment notification email template with multi-language support."""

    @staticmethod
    def get_subject(amount_dollars: float, language: Language = Language.ENGLISH) -> str:
        """Get the email subject in the specified language."""
        subjects = {
            Language.ENGLISH: f"New Payment - ${amount_dollars:.2f}",
            Language.SPANISH: f"Nuevo Pago - ${amount_dollars:.2f}",
        }
        return subjects.get(language, subjects[Language.ENGLISH])

    @staticmethod
    def get_greeting(provider_name: str, language: Language = Language.ENGLISH) -> str:
        """Get the greeting in the specified language."""
        greetings = {
            Language.ENGLISH: f"Hello {provider_name},",
            Language.SPANISH: f"Hola {provider_name},",
        }
        return greetings.get(language, greetings[Language.ENGLISH])

    @staticmethod
    def get_intro_text(language: Language = Language.ENGLISH) -> str:
        """Get the intro text in the specified language."""
        intros = {
            Language.ENGLISH: "We're pleased to inform you that a payment is heading your way.",
            Language.SPANISH: "Nos complace informarle que un pago está en camino hacia usted.",
        }
        return intros.get(language, intros[Language.ENGLISH])

    @staticmethod
    def get_email_header(language: Language = Language.ENGLISH) -> str:
        """Get the main email header/title in the specified language."""
        headers = {
            Language.ENGLISH: "New Payment Processed",
            Language.SPANISH: "Nuevo Pago Procesado",
        }
        return headers.get(language, headers[Language.ENGLISH])

    @staticmethod
    def get_payment_details_header(language: Language = Language.ENGLISH) -> str:
        """Get the payment details header in the specified language."""
        headers = {
            Language.ENGLISH: "Payment Details:",
            Language.SPANISH: "Detalles del Pago:",
        }
        return headers.get(language, headers[Language.ENGLISH])

    @staticmethod
    def get_field_labels(language: Language = Language.ENGLISH) -> Dict[str, str]:
        """Get field labels in the specified language."""
        labels = {
            Language.ENGLISH: {
                "child": "Child:",
                "amount": "Amount:",
                "payment_method": "Payment Method:",
            },
            Language.SPANISH: {
                "child": "Niño/a:",
                "amount": "Cantidad:",
                "payment_method": "Método de Pago:",
            },
        }
        return labels.get(language, labels[Language.ENGLISH])

    @staticmethod
    def get_payment_method_display(payment_method: str, language: Language = Language.ENGLISH) -> str:
        """Get payment method display text in the specified language."""
        if payment_method == PaymentMethod.CARD:
            displays = {
                Language.ENGLISH: "Virtual Card",
                Language.SPANISH: "Tarjeta Virtual",
            }
        else:  # ACH
            displays = {
                Language.ENGLISH: "Direct Deposit (ACH)",
                Language.SPANISH: "Depósito Directo (ACH)",
            }
        return displays.get(language, displays[Language.ENGLISH])

    @staticmethod
    def get_whats_next_header(language: Language = Language.ENGLISH) -> str:
        """Get the 'What's Next?' header in the specified language."""
        headers = {
            Language.ENGLISH: "What's Next?",
            Language.SPANISH: "¿Qué Sigue?",
        }
        return headers.get(language, headers[Language.ENGLISH])

    @staticmethod
    def get_card_instructions(language: Language = Language.ENGLISH) -> list[str]:
        """Get virtual card instructions in the specified language."""
        instructions = {
            Language.ENGLISH: [
                "Funds have been loaded onto your virtual card",
                "You can use your card immediately for purchases",
                "Check your card balance in your Chek account",
            ],
            Language.SPANISH: [
                "Los fondos se han cargado en su tarjeta virtual",
                "Puede usar su tarjeta inmediatamente para compras",
                "Consulte el saldo de su tarjeta en su cuenta Chek",
            ],
        }
        return instructions.get(language, instructions[Language.ENGLISH])

    @staticmethod
    def get_ach_instructions(language: Language = Language.ENGLISH) -> list[str]:
        """Get ACH instructions in the specified language."""
        instructions = {
            Language.ENGLISH: [
                "Funds are being transferred to your bank account",
                "Direct deposits typically arrive within 1-2 business days",
                "You'll receive a confirmation once the transfer is complete",
            ],
            Language.SPANISH: [
                "Los fondos están siendo transferidos a su cuenta bancaria",
                "Los depósitos directos generalmente llegan dentro de 1-2 días hábiles",
                "Recibirá una confirmación una vez que se complete la transferencia",
            ],
        }
        return instructions.get(language, instructions[Language.ENGLISH])

    @staticmethod
    def get_support_text(language: Language = Language.ENGLISH) -> str:
        """Get support text in the specified language."""
        texts = {
            Language.ENGLISH: "If you have any questions about this payment, please reach out to our support team.",
            Language.SPANISH: "Si tiene alguna pregunta sobre este pago, por favor comuníquese con nuestro equipo de soporte.",
        }
        return texts.get(language, texts[Language.ENGLISH])

    @staticmethod
    def get_signature(language: Language = Language.ENGLISH) -> str:
        """Get email signature in the specified language."""
        signatures = {
            Language.ENGLISH: "Best regards,<br>The CAP Team",
            Language.SPANISH: "Saludos cordiales,<br>El Equipo CAP",
        }
        return signatures.get(language, signatures[Language.ENGLISH])

    @staticmethod
    def get_footer(language: Language = Language.ENGLISH) -> str:
        """Get footer text in the specified language."""
        footers = {
            Language.ENGLISH: "This is an automated notification from the CAP portal system.",
            Language.SPANISH: "Esta es una notificación automática del sistema del portal CAP.",
        }
        return footers.get(language, footers[Language.ENGLISH])

    @classmethod
    def build_html_content(
        cls,
        provider_name: str,
        child_name: str,
        amount_cents: int,
        payment_method: str,
        language: Language = Language.ENGLISH,
    ) -> str:
        """Build the complete HTML email content in the specified language."""
        amount_dollars = amount_cents / 100
        labels = cls.get_field_labels(language)
        payment_method_display = cls.get_payment_method_display(payment_method, language)

        html_content = f"""
        <html>
            <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #b53363; border-bottom: 2px solid #364f3f; padding-bottom: 10px;">
                        {cls.get_email_header(language)}
                    </h2>

                    <p>{cls.get_greeting(provider_name, language)}</p>

                    <p>{cls.get_intro_text(language)}</p>

                    <div style="background-color: #f8f9fa; border-left: 4px solid #364f3f; padding: 15px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #2c3e50;">{cls.get_payment_details_header(language)}</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0;"><strong>{labels['child']}</strong></td>
                                <td style="padding: 8px 0;">{child_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0;"><strong>{labels['amount']}</strong></td>
                                <td style="padding: 8px 0; color: #364f3f; font-size: 18px;"><strong>${amount_dollars:.2f}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0;"><strong>{labels['payment_method']}</strong></td>
                                <td style="padding: 8px 0;">{payment_method_display}</td>
                            </tr>
        """

        html_content += f"""
                        </table>
                    </div>

                    <div style="background-color: #C9D1CC; padding: 15px; margin: 20px 0; border-radius: 5px; color: #000000;">
                        <p style="margin: 0;"><strong>{cls.get_whats_next_header(language)}</strong></p>
                        <ul style="margin: 10px 0 0 0; padding-left: 20px;">
        """

        if payment_method == PaymentMethod.CARD:
            for instruction in cls.get_card_instructions(language):
                html_content += f"                        <li>{instruction}</li>\n"
        else:  # ACH
            for instruction in cls.get_ach_instructions(language):
                html_content += f"                        <li>{instruction}</li>\n"

        html_content += f"""
                        </ul>
                    </div>

                    <p>{cls.get_support_text(language)}</p>

                    <p>{cls.get_signature(language)}</p>

                    <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
                    <p style="font-size: 12px; color: #666; text-align: center;">
                        {cls.get_footer(language)}<br>
                    </p>
                </div>
            </body>
        </html>
        """

        return html_content
