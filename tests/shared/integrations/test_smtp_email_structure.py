# -*- coding: utf-8 -*-
"""
backend/tests/shared/integrations/test_smtp_email_structure.py

Tests para verificar estructura de correos SMTP:
- Multipart/alternative (text/plain + text/html)
- Headers obligatorios (Date, Message-ID, From, To, Subject)
- HTML no contiene URL visible (solo en href)
- text/plain sí contiene URL completa

Autor: DoxAI
Creado: 2025-12-14
"""

import pytest
import re
from email.message import EmailMessage

from app.shared.integrations.smtp_email_sender import SMTPEmailSender


class TestActivationEmailStructure:
    """Tests para estructura del correo de activación."""

    @pytest.fixture
    def sender(self) -> SMTPEmailSender:
        """Crea instancia de SMTPEmailSender para tests."""
        return SMTPEmailSender(
            server="smtp.test.local",
            port=587,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=False,
            use_tls=True,
            frontend_url="https://doxai.juvare.mx",
        )

    def test_activation_email_has_text_plain_with_url(self, sender: SMTPEmailSender):
        """text/plain debe contener el activation_link completo."""
        html, text, used_template = sender._build_activation_body(
            full_name="Test User",
            activation_token="abc123xyz789"
        )
        
        expected_url = "https://doxai.juvare.mx/auth/activate?token=abc123xyz789"
        
        # text/plain debe contener URL completa
        assert expected_url in text, "text/plain debe contener el activation_link completo"
        
        # Verificar que text tiene contenido sustancial
        assert len(text) > 100, "text/plain debe tener contenido sustancial"
        assert "Estimado/a Test User" in text

    def test_activation_email_html_no_visible_url(self, sender: SMTPEmailSender):
        """HTML no debe mostrar URL como texto visible (solo en href)."""
        html, text, used_template = sender._build_activation_body(
            full_name="Test User",
            activation_token="abc123xyz789"
        )
        
        activation_url = "https://doxai.juvare.mx/auth/activate?token=abc123xyz789"
        
        # URL debe estar en href
        assert f'href="{activation_url}"' in html or f"href='{activation_url}'" in html, \
            "URL debe estar en atributo href"
        
        # URL NO debe aparecer como texto visible (fuera de href)
        # Removemos los atributos href para verificar que no aparece en texto visible
        html_without_href = re.sub(r'href=["\'][^"\']*["\']', 'href=""', html)
        assert activation_url not in html_without_href, \
            "URL no debe aparecer como texto visible en HTML (solo en href)"

    def test_email_message_has_required_headers(self, sender: SMTPEmailSender):
        """EmailMessage debe tener headers Date, Message-ID, From, To, Subject."""
        msg = sender.build_email_message(
            to_email="recipient@test.com",
            subject="Test Subject",
            html_body="<html><body>Test</body></html>",
            text_body="Test plain text"
        )
        
        # Verificar headers obligatorios
        assert msg["From"] is not None, "Header From es obligatorio"
        assert msg["To"] is not None, "Header To es obligatorio"
        assert msg["Subject"] is not None, "Header Subject es obligatorio"
        assert msg["Date"] is not None, "Header Date es obligatorio"
        assert msg["Message-ID"] is not None, "Header Message-ID es obligatorio"
        
        # Verificar formato de From (debe incluir nombre)
        assert "DoxAI" in msg["From"], "From debe incluir nombre del remitente"
        assert "doxai@juvare.mx" in msg["From"], "From debe incluir email"
        
        # Verificar formato de Message-ID
        assert msg["Message-ID"].startswith("<"), "Message-ID debe empezar con <"
        assert msg["Message-ID"].endswith(">"), "Message-ID debe terminar con >"

    def test_email_message_is_multipart_alternative(self, sender: SMTPEmailSender):
        """EmailMessage debe ser multipart/alternative con text/plain y text/html."""
        msg = sender.build_email_message(
            to_email="recipient@test.com",
            subject="Test Subject",
            html_body="<html><body><h1>Test HTML</h1></body></html>",
            text_body="Test plain text content"
        )
        
        # Debe ser multipart
        assert msg.is_multipart(), "Mensaje debe ser multipart"
        
        # Obtener partes
        parts = list(msg.iter_parts())
        assert len(parts) >= 2, "Debe tener al menos 2 partes (text/plain y text/html)"
        
        # Verificar tipos de contenido
        content_types = [part.get_content_type() for part in parts]
        assert "text/plain" in content_types, "Debe contener parte text/plain"
        assert "text/html" in content_types, "Debe contener parte text/html"
        
        # Verificar contenido de cada parte
        for part in parts:
            if part.get_content_type() == "text/plain":
                content = part.get_content()
                assert "Test plain text content" in content
            elif part.get_content_type() == "text/html":
                content = part.get_content()
                assert "<h1>Test HTML</h1>" in content

    def test_mask_token_hides_middle(self, sender: SMTPEmailSender):
        """_mask_token debe ocultar la parte media del token."""
        # Token largo
        masked = sender._mask_token("abcdefghijklmnop")
        assert masked == "abcd...mnop"
        
        # Token corto
        masked_short = sender._mask_token("abc")
        assert masked_short == "****"

    def test_activation_body_returns_template_flag(self, sender: SMTPEmailSender):
        """_build_activation_body debe retornar flag indicando si usó template."""
        # Sin template (sender no tiene templates_dir válido por defecto en test)
        sender.templates_dir = None
        html, text, used_template = sender._build_activation_body(
            full_name="User",
            activation_token="token123"
        )
        
        assert used_template is False, "Debe indicar que usó fallback"
        assert len(html) > 0
        assert len(text) > 0


class TestPasswordResetEmailStructure:
    """Tests para estructura del correo de reset de contraseña."""

    @pytest.fixture
    def sender(self) -> SMTPEmailSender:
        return SMTPEmailSender(
            server="smtp.test.local",
            port=587,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=False,
            frontend_url="https://doxai.juvare.mx",
        )

    def test_password_reset_has_token_in_text(self, sender: SMTPEmailSender):
        """text/plain debe contener el reset token."""
        sender.templates_dir = None  # Forzar fallback
        html, text, used_template = sender._build_password_reset_body(
            full_name="Test User",
            reset_token="RESET123"
        )
        
        assert "RESET123" in text, "text/plain debe contener el token de reset"
        assert "https://doxai.juvare.mx/auth/reset-password" in text


class TestWelcomeEmailStructure:
    """Tests para estructura del correo de bienvenida."""

    @pytest.fixture
    def sender(self) -> SMTPEmailSender:
        return SMTPEmailSender(
            server="smtp.test.local",
            port=587,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=False,
            frontend_url="https://doxai.juvare.mx",
        )

    def test_welcome_email_includes_credits(self, sender: SMTPEmailSender):
        """Email de bienvenida debe incluir cantidad de créditos."""
        sender.templates_dir = None  # Forzar fallback
        html, text, used_template = sender._build_welcome_body(
            full_name="Test User",
            credits_assigned=5
        )
        
        assert "5" in text, "text/plain debe mencionar cantidad de créditos"
        assert "5" in html, "HTML debe mencionar cantidad de créditos"
        assert "créditos" in text.lower() or "creditos" in text.lower()


class TestSMTPTLSBehavior:
    """Tests para verificar comportamiento correcto de TLS/SSL."""

    def test_use_tls_false_does_not_call_starttls(self, mocker):
        """Cuando use_tls=False, _send_sync NO debe llamar a starttls()."""
        from unittest.mock import MagicMock, patch
        
        sender = SMTPEmailSender(
            server="smtp.test.local",
            port=25,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=False,
            use_tls=False,  # IMPORTANTE: TLS desactivado
            frontend_url="https://doxai.juvare.mx",
        )
        
        # Mock SMTP class
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.ehlo.return_value = (250, b"OK")
        mock_smtp_instance.login.return_value = (235, b"Authentication successful")
        mock_smtp_instance.send_message.return_value = {}
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)
        
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            sender._send_sync(
                to_email="test@example.com",
                subject="Test",
                html_body="<html><body>Test</body></html>",
                text_body="Test"
            )
        
        # Verificar que starttls NO fue llamado
        mock_smtp_instance.starttls.assert_not_called()
        # Verificar que ehlo y login SÍ fueron llamados
        mock_smtp_instance.ehlo.assert_called()
        mock_smtp_instance.login.assert_called_once()

    def test_use_tls_true_calls_starttls(self, mocker):
        """Cuando use_tls=True, _send_sync DEBE llamar a starttls()."""
        from unittest.mock import MagicMock, patch
        
        sender = SMTPEmailSender(
            server="smtp.test.local",
            port=587,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=False,
            use_tls=True,  # TLS activado
            frontend_url="https://doxai.juvare.mx",
        )
        
        # Mock SMTP class
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.ehlo.return_value = (250, b"OK")
        mock_smtp_instance.starttls.return_value = (220, b"Ready to start TLS")
        mock_smtp_instance.login.return_value = (235, b"Authentication successful")
        mock_smtp_instance.send_message.return_value = {}
        mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_instance.__exit__ = MagicMock(return_value=False)
        
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            sender._send_sync(
                to_email="test@example.com",
                subject="Test",
                html_body="<html><body>Test</body></html>",
                text_body="Test"
            )
        
        # Verificar que starttls SÍ fue llamado
        mock_smtp_instance.starttls.assert_called_once()
        # Verificar que ehlo fue llamado 2 veces (antes y después de starttls)
        assert mock_smtp_instance.ehlo.call_count == 2

    def test_use_ssl_uses_smtp_ssl(self, mocker):
        """Cuando use_ssl=True, debe usar SMTP_SSL en lugar de SMTP."""
        from unittest.mock import MagicMock, patch
        
        sender = SMTPEmailSender(
            server="smtp.test.local",
            port=465,
            username="test@test.local",
            password="testpass",
            from_email="doxai@juvare.mx",
            from_name="DoxAI",
            use_ssl=True,  # SSL directo
            use_tls=False,
            frontend_url="https://doxai.juvare.mx",
        )
        
        # Mock SMTP_SSL class
        mock_smtp_ssl_instance = MagicMock()
        mock_smtp_ssl_instance.login.return_value = (235, b"Authentication successful")
        mock_smtp_ssl_instance.send_message.return_value = {}
        mock_smtp_ssl_instance.__enter__ = MagicMock(return_value=mock_smtp_ssl_instance)
        mock_smtp_ssl_instance.__exit__ = MagicMock(return_value=False)
        
        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_ssl_instance) as mock_smtp_ssl:
            sender._send_sync(
                to_email="test@example.com",
                subject="Test",
                html_body="<html><body>Test</body></html>",
                text_body="Test"
            )
        
        # Verificar que SMTP_SSL fue usado
        mock_smtp_ssl.assert_called_once()
        mock_smtp_ssl_instance.login.assert_called_once()
