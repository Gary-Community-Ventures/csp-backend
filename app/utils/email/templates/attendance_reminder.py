"""
Attendance reminder email template.
"""

from app.supabase.columns import Language
from app.utils.email.base_template import BaseEmailTemplate


class AttendanceReminderTemplate:
    """Attendance reminder email template with multi-language support."""

    @staticmethod
    def get_family_content(family_name: str, link: str, language: Language = Language.ENGLISH) -> str:
        """Get family attendance reminder content."""
        if language == Language.SPANISH:
            greeting = f"¡Hola, {family_name}!"
            main_content = f"""
            <p>Confirme los días de cuidado de la semana pasada y programe el cuidado para la semana siguiente (si aún no lo ha hecho) antes del final del día para que su proveedor pueda recibir su pago.</p>
            {BaseEmailTemplate.create_button(link, "Acceder a Su Portal")}
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una notificación automática del sistema del portal CAP."
        else:
            greeting = f"Hi {family_name}!"
            main_content = f"""
            <p>Please confirm the days of care for the past week and schedule care for the following week (if you haven't done so already) by the end of the day, so your provider can get paid.</p>
            {BaseEmailTemplate.create_button(link, "Access Your Portal")}
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
    def get_provider_content(provider_name: str, link: str, language: Language = Language.ENGLISH) -> str:
        """Get provider attendance reminder content."""
        if language == Language.SPANISH:
            greeting = f"¡Hola, {provider_name}!"
            main_content = f"""
            <p>Confirme la asistencia de todos los niños bajo su cuidado que reciben el subsidio CAP antes del final del día para que pueda recibir su pago a tiempo.</p>
            {BaseEmailTemplate.create_button(link, "Acceder a Su Portal")}
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una notificación automática del sistema del portal CAP."
        else:
            greeting = f"Hi {provider_name}!"
            main_content = f"""
            <p>Please confirm attendance for all children in your care who receive the CAP subsidy by the end of the day, so you can get paid on time.</p>
            {BaseEmailTemplate.create_button(link, "Access Your Portal")}
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
    def get_center_content(provider_name: str, link: str, language: Language = Language.ENGLISH) -> str:
        """Get center attendance reminder content."""
        if language == Language.SPANISH:
            greeting = f"¡Hola, {provider_name}!"
            main_content = f"""
            <p>Por favor, complete la lista de asistencia de todos los niños a su cargo que recibieron subsidio CAP durante el último mes antes del final de esta semana.</p>

            <div style="background-color: {BaseEmailTemplate.ACCENT_COLOR}; padding: 20px; margin: 25px 0; border-radius: 5px; border-left: 4px solid {BaseEmailTemplate.SECONDARY_COLOR};">
                <p style="margin: 0 0 15px 0; font-weight: bold; color: #000;">Puede enviarnos la asistencia de dos maneras:</p>
                <table width="100%" cellpadding="10" cellspacing="0">
                    <tr>
                        <td width="50%" style="vertical-align: top;">
                            <p style="margin: 0 0 8px 0; font-weight: bold; color: #000;">📧 Por correo electrónico</p>
                            <p style="margin: 0; color: #000;">Envíe la verificación a:<br>
                            <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR}; font-weight: bold;">support@capcolorado.org</a></p>
                        </td>
                        <td width="50%" style="vertical-align: top;">
                            <p style="margin: 0 0 8px 0; font-weight: bold; color: #000;">💻 A través del portal</p>
                            <p style="margin: 0; color: #000;">Acceda a su cuenta:<br>
                            <a href="{link}" style="color: {BaseEmailTemplate.PRIMARY_COLOR}; font-weight: bold;">Portal CAP</a></p>
                        </td>
                    </tr>
                </table>
            </div>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una notificación automática del sistema del portal CAP."
        else:
            greeting = f"Hi {provider_name}!"
            main_content = f"""
            <p>Please fill out attendance for all children in your care who receive CAP subsidy for the past month by the end of the week.</p>

            <div style="background-color: {BaseEmailTemplate.ACCENT_COLOR}; padding: 20px; margin: 25px 0; border-radius: 5px; border-left: 4px solid {BaseEmailTemplate.SECONDARY_COLOR};">
                <p style="margin: 0 0 15px 0; font-weight: bold; color: #000;">You can submit attendance in two ways:</p>
                <table width="100%" cellpadding="10" cellspacing="0">
                    <tr>
                        <td width="50%" style="vertical-align: top;">
                            <p style="margin: 0 0 8px 0; font-weight: bold; color: #000;">📧 Via Email</p>
                            <p style="margin: 0; color: #000;">Send verification to:<br>
                            <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR}; font-weight: bold;">support@capcolorado.org</a></p>
                        </td>
                        <td width="50%" style="vertical-align: top;">
                            <p style="margin: 0 0 8px 0; font-weight: bold; color: #000;">💻 Through Portal</p>
                            <p style="margin: 0; color: #000;">Access your account:<br>
                            <a href="{link}" style="color: {BaseEmailTemplate.PRIMARY_COLOR}; font-weight: bold;">CAP Portal</a></p>
                        </td>
                    </tr>
                </table>
            </div>
            """
            signature = None
            footer = None

        return BaseEmailTemplate.build(
            greeting=greeting,
            main_content=main_content,
            signature=signature,
            footer_text=footer,
        )
