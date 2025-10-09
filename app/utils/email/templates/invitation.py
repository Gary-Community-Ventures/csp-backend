"""
Invitation email templates.
"""

from app.supabase.columns import Language
from app.utils.email.base_template import BaseEmailTemplate


class InvitationTemplate:
    """Invitation email templates with multi-language support."""

    @staticmethod
    def get_provider_invitation_content(
        family_name: str, child_name: str, link: str, language: Language = Language.ENGLISH
    ) -> str:
        """Get family-to-provider invitation content."""
        if language == Language.SPANISH:
            greeting = "¡Hola!"
            main_content = f"""
            <p><strong>{family_name}</strong> lo ha invitado a unirse al programa piloto de accesibilidad al cuidado infantil <strong>Childcare Affordability Pilot (CAP)</strong> como proveedor de <strong>{child_name}</strong>, y nos encantaría tenerte a bordo!</p>

            <p>CAP es un programa que ayuda a las familias a pagar el cuidado infantil y a proveedores como usted a recibir su pago. Recibirá pagos a través de CAP, mantendrá sus rutinas de cuidado habituales y apoyará a las familias con las que ya trabaja, o a nuevas familias.</p>

            {BaseEmailTemplate.create_button(link, "Aceptar Invitación")}

            <p style="margin-top: 30px;"><strong>¿Tienes preguntas?</strong></p>
            <p>Escríbenos a <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a> o visita nuestro sitio web <a href="https://www.capcolorado.org/es/providers" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">capcolorado.org</a>.</p>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una invitación del programa piloto de accesibilidad al cuidado infantil (CAP)."
        else:
            greeting = "Hello!"
            main_content = f"""
            <p><strong>{family_name}</strong> has invited you to join the <strong>Childcare Affordability Pilot (CAP)</strong> as a provider for <strong>{child_name}</strong>—and we'd love to have you on board!</p>

            <p>CAP is a program that helps families pay for childcare and helps providers like you get paid. You'll receive payments through CAP, keep your usual care routines, and support families you already work with—or new ones.</p>

            {BaseEmailTemplate.create_button(link, "Accept Invitation")}

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

    @staticmethod
    def get_family_invitation_content(provider_name: str, link: str, language: Language = Language.ENGLISH) -> str:
        """Get provider-to-family invitation content."""
        if language == Language.SPANISH:
            greeting = "¡Hola!"
            main_content = f"""
            <p><strong>{provider_name}</strong> lo ha invitado a unirse al <strong>Programa Piloto Childcare Affordability Pilot (CAP)</strong> como familia participante.</p>

            {BaseEmailTemplate.create_info_box(
                '<p style="margin: 0; font-size: 18px; color: #000;"><strong>¡Acceda hasta $1,400 por mes para pagar el cuidado infantil!</strong></p>'
            )}

            <p>Si presenta su solicitud y su solicitud es aprobada, CAP le proporcionará fondos que puede usar para pagar a <strong>{provider_name}</strong> o otros cuidadores que participen en el programa piloto.</p>

            {BaseEmailTemplate.create_button(link, "Aceptar Invitación y Aplicar")}

            <p style="margin-top: 30px;"><strong>¿Tienes preguntas?</strong></p>
            <p>Escríbenos a <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></p>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una invitación del programa piloto de accesibilidad al cuidado infantil (CAP)."
        else:
            greeting = "Hello!"
            main_content = f"""
            <p><strong>{provider_name}</strong> has invited you to join the <strong>Childcare Affordability Pilot (CAP)</strong> as a participating family.</p>

            {BaseEmailTemplate.create_info_box(
                '<p style="margin: 0; font-size: 18px; color: #000;"><strong>Access up to $1,400 per month to pay for childcare!</strong></p>'
            )}

            <p>If you apply and are approved, CAP provides funds you can use to pay <strong>{provider_name}</strong> or other caregivers that participate in the pilot.</p>

            {BaseEmailTemplate.create_button(link, "Accept Invitation & Apply")}

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
