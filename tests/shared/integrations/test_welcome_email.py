# -*- coding: utf-8 -*-
"""
Tests para el correo de bienvenida.
Valida que se envíe con los créditos correctos y use el template adecuado.
"""

import pytest


class TestWelcomeEmailBuild:
    """Tests para _build_welcome_body."""

    def test_welcome_email_with_template_uses_correct_placeholders(self):
        """El template debe usar user_name y frontend_url."""
        from app.shared.integrations.smtp_email_sender import SMTPEmailSender

        sender = SMTPEmailSender(
            server="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            from_email="test@test.com",
            frontend_url="https://app.doxai.com",
            templates_dir=None,  # Usa default templates si existe
        )

        html, text, _ = sender._build_welcome_body("Carlos García", 5)

        # Verificar contenido del mensaje
        assert "Carlos García" in html or "Carlos" in html
        assert "5" in html
        assert "créditos" in html.lower()
        
        # Text también debe tener info correcta
        assert "5" in text
        assert "créditos" in text.lower()

    def test_welcome_email_fallback_shows_credits(self):
        """El fallback HTML debe mostrar los créditos correctamente."""
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

        html, text, _ = sender._build_welcome_body("María López", 5)

        # Verificar que muestra los 5 créditos
        assert "5 créditos" in html or "5 créditos gratuitos" in html
        assert "María López" in html
        assert "app.doxai.com" in html  # Link de login
        
        # Text fallback
        assert "5" in text
        assert "María López" in text

    def test_welcome_email_fallback_without_frontend_url(self):
        """El fallback sin frontend_url no incluye link pero sí créditos."""
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

        html, text, _ = sender._build_welcome_body("Pedro Sánchez", 5)

        # Debe mostrar créditos aunque no haya link
        assert "5" in html
        assert "créditos" in html.lower()
        assert "Pedro Sánchez" in html
        
        # No debe tener link href vacío
        assert 'href=""' not in html

    def test_welcome_email_default_user_name(self):
        """Si no hay nombre, usa 'Usuario' como default."""
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

        html, text, _ = sender._build_welcome_body("", 5)

        assert "Usuario" in html
        assert "Usuario" in text


class TestWelcomeEmailIntegration:
    """Tests de integración con el flujo de activación."""

    @pytest.mark.asyncio
    async def test_welcome_email_called_after_activation(self):
        """El correo de bienvenida se envía después de activar la cuenta."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.modules.auth.services.activation_flow_service import ActivationFlowService
        
        # Mock del email sender
        mock_email_sender = MagicMock()
        mock_email_sender.send_welcome_email = AsyncMock()
        
        # Mock de la db session
        mock_db = AsyncMock()
        
        # Mock del activation service result
        mock_activation_result = {
            "code": "ACCOUNT_ACTIVATED",
            "message": "Cuenta activada",
            "credits_assigned": 5,
        }
        
        # Mock del usuario
        mock_user = MagicMock()
        mock_user.user_id = 123
        mock_user.user_email = "test@example.com"
        mock_user.user_full_name = "Test User"
        
        with patch.object(ActivationFlowService, '__init__', lambda self, db, email_sender: None):
            service = ActivationFlowService.__new__(ActivationFlowService)
            service.db = mock_db
            service.email_sender = mock_email_sender
            service.settings = MagicMock()
            service.activation_service = AsyncMock()
            service.activation_service.activate_account = AsyncMock(return_value=mock_activation_result)
            service.user_service = AsyncMock()
            service.user_service.get_by_email = AsyncMock(return_value=mock_user)
            
            # Ejecutar activación con email hint
            result = await service.activate_account({
                "token": "valid-token",
                "email": "test@example.com"
            })
            
            # Verificar que se llamó send_welcome_email con kwargs
            mock_email_sender.send_welcome_email.assert_called_once_with(
                to_email="test@example.com",
                full_name="Test User",
                credits_assigned=5,
            )
            
            # Verificar respuesta
            assert result["code"] == "ACCOUNT_ACTIVATED"
            assert result["credits_assigned"] == 5

    @pytest.mark.asyncio
    async def test_welcome_email_not_sent_without_email_hint(self):
        """El correo de bienvenida NO se envía si no hay email hint."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.modules.auth.services.activation_flow_service import ActivationFlowService
        
        mock_email_sender = MagicMock()
        mock_email_sender.send_welcome_email = AsyncMock()
        
        mock_activation_result = {
            "code": "ACCOUNT_ACTIVATED",
            "message": "Cuenta activada",
            "credits_assigned": 5,
        }
        
        with patch.object(ActivationFlowService, '__init__', lambda self, db, email_sender: None):
            service = ActivationFlowService.__new__(ActivationFlowService)
            service.db = AsyncMock()
            service.email_sender = mock_email_sender
            service.settings = MagicMock()
            service.activation_service = AsyncMock()
            service.activation_service.activate_account = AsyncMock(return_value=mock_activation_result)
            service.user_service = AsyncMock()
            
            # Ejecutar activación SIN email hint
            result = await service.activate_account({
                "token": "valid-token",
            })
            
            # NO debe llamar a send_welcome_email
            mock_email_sender.send_welcome_email.assert_not_called()
            
            # Pero la activación sí debe completarse
            assert result["code"] == "ACCOUNT_ACTIVATED"
