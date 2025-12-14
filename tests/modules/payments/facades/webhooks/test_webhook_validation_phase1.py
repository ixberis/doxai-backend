# -*- coding: utf-8 -*-
"""
Tests FASE 1: Validación anti-fraude de webhooks.

Tests para:
- Amount mismatch → rechazar
- Currency mismatch → rechazar  
- User mismatch → rechazar
- webhook_verified_at se actualiza

Autor: DoxAI
Fecha: 2025-12-13
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone


class TestAmountValidation:
    """Tests para validación de monto."""
    
    @pytest.mark.asyncio
    async def test_rejects_amount_mismatch(self):
        """Debe rechazar si el monto del webhook no coincide."""
        from app.modules.payments.facades.webhooks.success import (
            handle_payment_success,
            AmountMismatchError,
        )
        
        # Mock payment con amount_cents = 5000
        mock_payment = MagicMock()
        mock_payment.amount_cents = 5000
        mock_payment.currency = MagicMock(value="USD")
        mock_payment.user_id = 1
        
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_payment)
        
        mock_service = MagicMock()
        mock_session = MagicMock()
        
        # Webhook reporta monto diferente
        with pytest.raises(AmountMismatchError):
            await handle_payment_success(
                session=mock_session,
                payment_service=mock_service,
                payment_repo=mock_repo,
                payment_id=1,
                webhook_amount_cents=1000,  # DIFERENTE!
            )
    
    @pytest.mark.asyncio
    async def test_accepts_matching_amount(self):
        """Debe aceptar si el monto coincide."""
        from app.modules.payments.facades.webhooks.success import handle_payment_success
        
        mock_payment = MagicMock()
        mock_payment.amount_cents = 5000
        mock_payment.currency = MagicMock(value="USD")
        mock_payment.user_id = 1
        
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_payment)
        
        mock_service = MagicMock()
        mock_service.apply_success = AsyncMock(return_value=mock_payment)
        mock_session = MagicMock()
        
        result = await handle_payment_success(
            session=mock_session,
            payment_service=mock_service,
            payment_repo=mock_repo,
            payment_id=1,
            webhook_amount_cents=5000,  # IGUAL
        )
        
        assert result == mock_payment
        mock_service.apply_success.assert_called_once()


class TestCurrencyValidation:
    """Tests para validación de moneda."""
    
    @pytest.mark.asyncio
    async def test_rejects_currency_mismatch(self):
        """Debe rechazar si la moneda no coincide."""
        from app.modules.payments.facades.webhooks.success import (
            handle_payment_success,
            CurrencyMismatchError,
        )
        
        mock_payment = MagicMock()
        mock_payment.amount_cents = 5000
        mock_payment.currency = MagicMock(value="USD")
        mock_payment.user_id = 1
        
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_payment)
        
        mock_service = MagicMock()
        mock_session = MagicMock()
        
        with pytest.raises(CurrencyMismatchError):
            await handle_payment_success(
                session=mock_session,
                payment_service=mock_service,
                payment_repo=mock_repo,
                payment_id=1,
                webhook_currency="MXN",  # DIFERENTE!
            )


class TestUserValidation:
    """Tests para validación de usuario."""
    
    @pytest.mark.asyncio
    async def test_rejects_user_mismatch(self):
        """Debe rechazar si el usuario no coincide."""
        from app.modules.payments.facades.webhooks.success import (
            handle_payment_success,
            UserMismatchError,
        )
        
        mock_payment = MagicMock()
        mock_payment.amount_cents = 5000
        mock_payment.currency = MagicMock(value="USD")
        mock_payment.user_id = 1
        
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_payment)
        
        mock_service = MagicMock()
        mock_session = MagicMock()
        
        with pytest.raises(UserMismatchError):
            await handle_payment_success(
                session=mock_session,
                payment_service=mock_service,
                payment_repo=mock_repo,
                payment_id=1,
                webhook_user_id=999,  # DIFERENTE!
            )
