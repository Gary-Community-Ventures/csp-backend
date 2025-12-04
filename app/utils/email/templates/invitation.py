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
        elif language == Language.RUSSIAN:
            greeting = "Здравствуйте!"
            main_content = f"""
            <p><strong>{family_name}</strong> приглашает вас присоединиться к пилотной программе <strong>Childcare Affordability Pilot (CAP)</strong> в качестве воспитателя для <strong>{child_name}</strong> — мы будем рады видеть вас!</p>

            <p>CAP — это программа, которая помогает семьям оплачивать уход за детьми и помогает воспитателям, таким как вы, получать оплату. Вы будете получать выплаты через CAP, сохраните привычный режим ухода и будете поддерживать семьи, с которыми уже работаете, или новые семьи.</p>

            {BaseEmailTemplate.create_button(link, "Принять Приглашение")}

            <p style="margin-top: 30px;"><strong>Есть вопросы?</strong></p>
            <p>Напишите нам на <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a> или посетите наш сайт <a href="https://www.capcolorado.org/en/providers" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">capcolorado.org</a>.</p>
            """
            signature = "С уважением,<br>Команда CAP"
            footer = "Это приглашение от пилотной программы доступности ухода за детьми (CAP)."
        elif language == Language.ARABIC:
            greeting = "مرحباً!"
            main_content = f"""
            <p>لقد دعاك <strong>{family_name}</strong> للانضمام إلى البرنامج التجريبي <strong>Childcare Affordability Pilot (CAP)</strong> كمقدم رعاية لـ <strong>{child_name}</strong> — ونحن سعداء بانضمامك!</p>

            <p>CAP هو برنامج يساعد العائلات على دفع تكاليف رعاية الأطفال ويساعد مقدمي الرعاية مثلك على الحصول على أجرهم. ستتلقى المدفوعات من خلال CAP، وستحافظ على روتين الرعاية المعتاد، وستدعم العائلات التي تعمل معها بالفعل أو عائلات جديدة.</p>

            {BaseEmailTemplate.create_button(link, "قبول الدعوة")}

            <p style="margin-top: 30px;"><strong>هل لديك أسئلة؟</strong></p>
            <p>راسلنا على <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a> أو قم بزيارة موقعنا <a href="https://www.capcolorado.org/en/providers" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">capcolorado.org</a>.</p>
            """
            signature = "مع أطيب التحيات،<br>فريق CAP"
            footer = "هذه دعوة من البرنامج التجريبي لتوفير رعاية الأطفال (CAP)."
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
        elif language == Language.RUSSIAN:
            greeting = "Здравствуйте!"
            main_content = f"""
            <p><strong>{provider_name}</strong> приглашает вас присоединиться к <strong>пилотной программе Childcare Affordability Pilot (CAP)</strong> в качестве участвующей семьи.</p>

            {BaseEmailTemplate.create_info_box(
                '<p style="margin: 0; font-size: 18px; color: #000;"><strong>Получите до $1,400 в месяц на оплату ухода за детьми!</strong></p>'
            )}

            <p>Если вы подадите заявку и она будет одобрена, CAP предоставит средства, которые вы сможете использовать для оплаты услуг <strong>{provider_name}</strong> или других воспитателей, участвующих в пилотной программе.</p>

            {BaseEmailTemplate.create_button(link, "Принять Приглашение и Подать Заявку")}

            <p style="margin-top: 30px;"><strong>Есть вопросы?</strong></p>
            <p>Напишите нам на <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></p>
            """
            signature = "С уважением,<br>Команда CAP"
            footer = "Это приглашение от пилотной программы доступности ухода за детьми (CAP)."
        elif language == Language.ARABIC:
            greeting = "مرحباً!"
            main_content = f"""
            <p>لقد دعاك <strong>{provider_name}</strong> للانضمام إلى <strong>البرنامج التجريبي Childcare Affordability Pilot (CAP)</strong> كعائلة مشاركة.</p>

            {BaseEmailTemplate.create_info_box(
                '<p style="margin: 0; font-size: 18px; color: #000;"><strong>احصل على ما يصل إلى $1,400 شهرياً لدفع تكاليف رعاية الأطفال!</strong></p>'
            )}

            <p>إذا تقدمت بطلب وتمت الموافقة عليه، سيوفر لك CAP أموالاً يمكنك استخدامها لدفع أجر <strong>{provider_name}</strong> أو مقدمي رعاية آخرين يشاركون في البرنامج التجريبي.</p>

            {BaseEmailTemplate.create_button(link, "قبول الدعوة والتقديم")}

            <p style="margin-top: 30px;"><strong>هل لديك أسئلة؟</strong></p>
            <p>راسلنا على <a href="mailto:support@capcolorado.org" style="color: {BaseEmailTemplate.PRIMARY_COLOR};">support@capcolorado.org</a></p>
            """
            signature = "مع أطيب التحيات،<br>فريق CAP"
            footer = "هذه دعوة من البرنامج التجريبي لتوفير رعاية الأطفال (CAP)."
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
