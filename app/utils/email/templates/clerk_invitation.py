"""
Clerk invitation email templates.
"""

from app.supabase.columns import Language
from app.utils.email.base_template import BaseEmailTemplate


class ClerkInvitationTemplate:
    """Clerk invitation email templates with multi-language support."""

    @staticmethod
    def get_subject(language: Language = Language.ENGLISH) -> str:
        """Get subject line for Clerk invitation."""
        if language == Language.SPANISH:
            return "¡Ha sido aprobado para el Portal de CAP Colorado!"
        else:
            return "You've Been Approved for CAP Colorado Portal"

    @staticmethod
    def get_family_invitation_content(invitation_url: str, language: Language = Language.ENGLISH) -> str:
        """
        Get Clerk invitation content for families.

        Args:
            invitation_url: Clerk invitation URL for account creation
            language: Language preference for the email

        Returns:
            HTML content for the email
        """
        if language == Language.SPANISH:
            greeting = "¡Hola!"
            main_content = f"""
            <p>Su solicitud ha sido aprobada y ahora tiene acceso al <strong>Portal de CAP Colorado</strong>.</p>

            <p>CAP es un programa que ayuda a las familias a pagar el cuidado infantil proporcionando hasta <strong>$1,400 por mes</strong> para cubrir los costos del cuidado.</p>

            <p>Haga clic en el botón de abajo para crear su cuenta y comenzar:</p>

            {BaseEmailTemplate.create_button(invitation_url, "Crear su Cuenta")}

            <p style="margin-top: 30px;"><strong>¿Tienes preguntas?</strong></p>
            <p>Escríbenos a <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></p>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una invitación del programa piloto de accesibilidad al cuidado infantil (CAP)."
        else:
            greeting = "Hello!"
            main_content = f"""
            <p>Your application has been approved and you now have access to the <strong>CAP Colorado Portal</strong>.</p>

            <p>CAP is a program that helps families pay for childcare by providing up to <strong>$1,400 per month</strong> to cover care costs.</p>

            <p>Click the button below to create your account and get started:</p>

            {BaseEmailTemplate.create_button(invitation_url, "Create Your Account")}

            <p style="margin-top: 30px;"><strong>Questions?</strong></p>
            <p>Email us at <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></p>
            """
            signature = None
            footer = None

        return BaseEmailTemplate.build(
            greeting=greeting,
            main_content=main_content,
            signature=signature,
            footer_text=footer,
        )

    @staticmethod
    def get_provider_invitation_content(
        invitation_url: str, language: Language = Language.ENGLISH, provider_name: str = None
    ) -> str:
        """
        Get Clerk invitation content for providers.

        Args:
            invitation_url: Clerk invitation URL for account creation
            language: Language preference for the email
            provider_name: Provider's first name for personalization

        Returns:
            HTML content for the email
        """
        if language == Language.SPANISH:
            greeting = f"¡Hola{' ' + provider_name if provider_name else ''}!"
            main_content = f"""
            <p>Su solicitud ha sido aprobada y ahora tiene acceso al <strong>Portal de CAP Colorado</strong> como proveedor de cuidado infantil.</p>

            <p>CAP es un programa que ayuda a las familias a pagar el cuidado infantil y a proveedores como usted a recibir pagos de manera fácil y confiable.</p>

            <p>Haga clic en el botón de abajo para crear su cuenta y comenzar:</p>

            {BaseEmailTemplate.create_button(invitation_url, "Crear su Cuenta")}

            <p style="margin-top: 30px;"><strong>¿Tienes preguntas?</strong></p>
            <p>Escríbenos a <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a> o visita nuestro sitio web <a href="https://www.capcolorado.org/es/providers" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">capcolorado.org</a>.</p>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una invitación del programa piloto de accesibilidad al cuidado infantil (CAP)."
        else:
            greeting = f"Hello{' ' + provider_name if provider_name else ''}!"
            main_content = f"""
            <p>Your application has been approved and you now have access to the <strong>CAP Colorado Portal</strong> as a childcare provider.</p>

            <p>CAP is a program that helps families pay for childcare and helps providers like you receive payments easily and reliably.</p>

            <p>Click the button below to create your account and get started:</p>

            {BaseEmailTemplate.create_button(invitation_url, "Create Your Account")}

            <p style="margin-top: 30px;"><strong>Questions?</strong></p>
            <p>Email us at <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a> or visit our website <a href="https://www.capcolorado.org/en/providers" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">capcolorado.org</a>.</p>
            """
            signature = None
            footer = None

        return BaseEmailTemplate.build(
            greeting=greeting,
            main_content=main_content,
            signature=signature,
            footer_text=footer,
        )
