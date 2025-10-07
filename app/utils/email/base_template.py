"""
Base email template for external-facing emails with professional styling and branding.
"""

from flask import current_app


class BaseEmailTemplate:
    """Base template for all external-facing emails with CAP branding."""

    # Brand colors from payment notification template
    PRIMARY_COLOR = "#b53363"  # Pink/Magenta
    SECONDARY_COLOR = "#364f3f"  # Dark green
    ACCENT_COLOR = "#C9D1CC"  # Light gray-green
    BACKGROUND_COLOR = "#f8f9fa"  # Light background
    TEXT_COLOR = "#333"
    LIGHT_TEXT_COLOR = "#666"

    @classmethod
    def get_logo_url(cls) -> str:
        """Get the logo URL from the backend domain."""
        backend_domain = current_app.config.get("BACKEND_DOMAIN", "http://localhost:5000")
        return f"{backend_domain}/static/images/cap-logo.png"

    @classmethod
    def build(
        cls,
        greeting: str,
        main_content: str,
        signature: str = None,
        footer_text: str = None,
    ) -> str:
        """
        Build a complete HTML email using the base template.

        Args:
            greeting: Opening greeting (e.g., "Hi John,")
            main_content: Main body content (HTML allowed)
            signature: Optional custom signature (defaults to "Best regards,<br>The CAP Team")
            footer_text: Optional custom footer (defaults to standard disclaimer)

        Returns:
            Complete HTML email string
        """
        if signature is None:
            signature = "Best regards,<br>The CAP Team"

        if footer_text is None:
            footer_text = "This is an automated notification from the CAP portal system."

        logo_url = cls.get_logo_url()

        html = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: sans-serif; line-height: 1.6; color: {cls.TEXT_COLOR}; margin: 0; padding: 0; background-color: #f4f4f4;">
                <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 20px 0;">
                    <tr>
                        <td align="center">
                            <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                <!-- Header with logo -->
                                <tr>
                                    <td style="background-color: white; padding: 30px 20px; text-align: center; border-bottom: 3px solid {cls.SECONDARY_COLOR};">
                                        <img src="{logo_url}" alt="CAP Logo" style="width: 120px; height: 120px;">
                                    </td>
                                </tr>

                                <!-- Main content -->
                                <tr>
                                    <td style="padding: 40px 30px;">
                                        {"<p style='margin: 0 0 20px 0;'>" + greeting + "</p>" if greeting else ""}

                                        {main_content}

                                        <p style="margin: 30px 0 0 0;">{signature}</p>
                                    </td>
                                </tr>

                                <!-- Footer -->
                                <tr>
                                    <td style="background-color: {cls.BACKGROUND_COLOR}; padding: 20px 30px; border-top: 2px solid {cls.SECONDARY_COLOR};">
                                        <p style="font-size: 12px; color: {cls.LIGHT_TEXT_COLOR}; text-align: center; margin: 0;">
                                            {footer_text}
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """

        return html

    @classmethod
    def create_button(cls, url: str, text: str, color: str = None) -> str:
        """
        Create a styled button/link.

        Args:
            url: Link destination
            text: Button text
            color: Optional custom color (defaults to PRIMARY_COLOR)

        Returns:
            HTML for styled button
        """
        if color is None:
            color = cls.PRIMARY_COLOR

        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
            <tr>
                <td align="center">
                    <a href="{url}" style="display: inline-block; background-color: {color}; color: white; text-decoration: none; padding: 14px 30px; border-radius: 5px; font-weight: bold; font-size: 16px;">
                        {text}
                    </a>
                </td>
            </tr>
        </table>
        """

    @classmethod
    def create_info_box(cls, content: str, background_color: str = None) -> str:
        """
        Create a highlighted info box.

        Args:
            content: HTML content for the box
            background_color: Optional custom background (defaults to ACCENT_COLOR)

        Returns:
            HTML for info box
        """
        if background_color is None:
            background_color = cls.ACCENT_COLOR

        return f"""
        <div style="background-color: {background_color}; border-left: 4px solid {cls.SECONDARY_COLOR}; padding: 20px; margin: 20px 0; border-radius: 5px;">
            {content}
        </div>
        """
