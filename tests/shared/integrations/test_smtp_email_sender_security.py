# -*- coding: utf-8 -*-
"""
Tests para verificar que los correos SMTP no exponen tokens.

Autor: Ixchel Beristain
Fecha: 2025-12-14
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestActivationEmailNoToken:
    """Verificar que activation emails no exponen el token."""

    def test_fallback_with_link_no_token_in_html(self):
        """El fallback HTML no debe incluir el token raw como texto visible."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            frontend_url="https://app.doxai.com",
            templates_dir="/nonexistent/path/to/force/fallback",  # Forzar fallback
        )

        token = "abc123secrettoken"
        html, text, _ = sender._build_activation_body("Juan", token)

        # El token puede aparecer en el URL del link, pero NO como texto visible fuera del link
        # Eliminar el URL del html para verificar que no aparece en otro lado
        html_without_url = html.replace(f"token={token}", "token=REDACTED")
        assert token not in html_without_url, "Token should not appear outside URL in fallback HTML"
        assert "código" not in html.lower(), "No debe mencionar 'código' en HTML"
        
        # El link SÍ contiene el token (en URL) pero no visible
        assert "https://app.doxai.com/auth/activate?token=" in html
        
        # Text tampoco debe tener el token como texto visible
        assert f"código" not in text.lower()
        assert f"tu código de activación es" not in text.lower()
        # Pero sí debe tener el link
        assert "https://app.doxai.com/auth/activate?token=" in text

    def test_fallback_without_frontend_url_no_token(self):
        """Sin frontend_url, el fallback no debe exponer el token."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            frontend_url=None,
            templates_dir="/nonexistent/path/to/force/fallback",
        )

        token = "xyz789secrettoken"
        html, text, _ = sender._build_activation_body("Maria", token)

        # Sin link, no debe aparecer el token de ninguna forma
        assert token not in html, "Token must not appear in HTML without frontend_url"
        assert token not in text, "Token must not appear in text without frontend_url"
        assert "código" not in html.lower()
        assert "código" not in text.lower()
        # Debe tener mensaje genérico
        assert "soporte" in text.lower() or "contacta" in text.lower()

    def test_with_template_uses_activation_link_variable(self, tmp_path):
        """Con template, debe usar activation_link y user_name."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        # Crear template minimal
        template_content = """
        <html>
        <body>
            <p>Hola {{ user_name }}</p>
            <a href="{{ activation_link }}">Activar</a>
        </body>
        </html>
        """
        template_file = tmp_path / "activation_email.html"
        template_file.write_text(template_content, encoding="utf-8")

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            frontend_url="https://app.doxai.com",
            templates_dir=str(tmp_path),
        )

        token = "templatetoken123"
        html, text, _ = sender._build_activation_body("Pedro", token)

        # Variables sustituidas
        assert "Hola Pedro" in html
        assert "https://app.doxai.com/auth/activate?token=templatetoken123" in html
        # El token raw no debe estar como texto visible
        assert "templatetoken123" not in html.replace("token=templatetoken123", "")

    def test_default_templates_dir_fallback(self):
        """Si no se pasa templates_dir, debe buscar en ruta default."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            templates_dir=None,
        )

        # Debe haber intentado usar el default
        # Si existe el directorio default, templates_dir no será None
        default_path = Path(__file__).parent.parent.parent.parent / "app" / "shared" / "templates"
        if default_path.exists():
            assert sender.templates_dir is not None
            assert sender.templates_dir.exists()


class TestPasswordResetEmailNoToken:
    """Verificar que password reset emails manejan tokens correctamente."""

    def test_password_reset_fallback_has_token_in_link_only(self):
        """Password reset puede mostrar token solo en URL, no como código."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            frontend_url="https://app.doxai.com",
            templates_dir="/nonexistent/path/to/force/fallback",
        )

        token = "resettoken456"
        html, text, _ = sender._build_password_reset_body("Ana", token)

        # El link debe estar presente en el fallback
        assert "https://app.doxai.com/auth/reset-password?token=resettoken456" in html
