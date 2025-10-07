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
            {BaseEmailTemplate.create_button(link, "Acceder a Su Portal")}
            <p style="text-align: center; margin-top: 15px;">
                <small>O envíenos la verificación por correo electrónico: <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></small>
            </p>
            """
            signature = "Saludos cordiales,<br>El Equipo CAP"
            footer = "Esta es una notificación automática del sistema del portal CAP."
        else:
            greeting = f"Hi {provider_name}!"
            main_content = f"""
            <p>Please fill out attendance for all children in your care who receive CAP subsidy for the past month by the end of the week.</p>
            {BaseEmailTemplate.create_button(link, "Access Your Portal")}
            <p style="text-align: center; margin-top: 15px;">
                <small>Or send us the verification via email: <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></small>
            </p>
            """
            signature = None
            footer = None

        return BaseEmailTemplate.build(
            greeting=greeting,
            main_content=main_content,
            signature=signature,
            footer_text=footer,
        )
