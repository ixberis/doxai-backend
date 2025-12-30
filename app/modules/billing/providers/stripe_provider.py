# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/providers/stripe_provider.py

Proveedor Stripe para checkout de créditos prepagados.

Crea Stripe Checkout Sessions y maneja la integración con el gateway.

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from app.shared.config.settings_payments import get_payments_settings

# Conditional import for environments without stripe SDK
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None  # type: ignore
    STRIPE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class StripeSessionResult:
    """Resultado de crear una sesión de checkout en Stripe."""
    checkout_url: str
    session_id: str
    provider: str = "stripe"


class StripeProvider:
    """
    Proveedor de pagos Stripe para créditos prepagados.
    
    Crea Checkout Sessions con line items dinámicos basados en
    los paquetes de créditos definidos.
    """
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Inicializa el proveedor Stripe.
        
        Args:
            secret_key: Stripe secret key. Si no se proporciona,
                        se intenta cargar desde settings o env.
        """
        self._secret_key = secret_key or self._load_secret_key()
        if self._secret_key and STRIPE_AVAILABLE:
            stripe.api_key = self._secret_key
    
    def _load_secret_key(self) -> Optional[str]:
        """Carga la secret key desde settings o env."""
        settings = get_payments_settings()
        key = settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY")
        if not key:
            logger.warning("STRIPE_SECRET_KEY not configured")
        return key
    
    @property
    def is_configured(self) -> bool:
        """Retorna True si Stripe está configurado y el SDK está disponible."""
        return STRIPE_AVAILABLE and bool(self._secret_key)
    
    async def create_checkout_session(
        self,
        *,
        intent_id: int,
        user_id: int,
        package_id: str,
        package_name: str,
        credits_amount: int,
        price_cents: int,
        currency: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> StripeSessionResult:
        """
        Crea una Stripe Checkout Session para compra de créditos.
        
        Args:
            intent_id: ID del checkout intent (para metadata)
            user_id: ID del usuario
            package_id: ID del paquete (e.g., 'pkg_pro')
            package_name: Nombre del paquete para mostrar
            credits_amount: Cantidad de créditos
            price_cents: Precio en centavos
            currency: Código de moneda (MXN, USD, etc.)
            success_url: URL de redirección en éxito
            cancel_url: URL de redirección en cancelación
            customer_email: Email del cliente (opcional)
            
        Returns:
            StripeSessionResult con checkout_url y session_id
            
        Raises:
            stripe.error.StripeError: Si hay error con Stripe API
            ValueError: Si Stripe no está configurado
        """
        if not self.is_configured:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY.")
        
        logger.info(
            "Creating Stripe checkout session: intent=%s user=%s package=%s",
            intent_id, user_id, package_id,
        )
        
        # Construir line item dinámico (no requiere producto pre-creado)
        line_item = {
            "price_data": {
                "currency": currency.lower(),
                "unit_amount": price_cents,
                "product_data": {
                    "name": f"DoxAI Créditos - {package_name}",
                    "description": f"{credits_amount:,} créditos para análisis de documentos",
                    "metadata": {
                        "package_id": package_id,
                        "credits": str(credits_amount),
                    },
                },
            },
            "quantity": 1,
        }
        
        # Metadata para webhook
        metadata = {
            "checkout_intent_id": str(intent_id),
            "user_id": str(user_id),
            "package_id": package_id,
            "credits_amount": str(credits_amount),
            "source": "doxai_billing",
        }
        
        # Crear sesión
        session_params = {
            "mode": "payment",
            "payment_method_types": ["card"],
            "line_items": [line_item],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "client_reference_id": str(intent_id),
        }
        
        if customer_email:
            session_params["customer_email"] = customer_email
        
        # Ejecutar en threadpool para no bloquear el event loop
        from fastapi.concurrency import run_in_threadpool
        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            **session_params,
        )
        
        logger.info(
            "Stripe checkout session created: session_id=%s intent=%s",
            session.id, intent_id,
        )
        
        return StripeSessionResult(
            checkout_url=session.url,
            session_id=session.id,
        )


async def create_stripe_checkout_session(
    *,
    intent_id: int,
    user_id: int,
    package_id: str,
    package_name: str,
    credits_amount: int,
    price_cents: int,
    currency: str,
    success_url: str,
    cancel_url: str,
    customer_email: Optional[str] = None,
) -> StripeSessionResult:
    """
    Función helper para crear sesión sin instanciar proveedor.
    
    Wrapper conveniente sobre StripeProvider.create_checkout_session().
    """
    provider = StripeProvider()
    return await provider.create_checkout_session(
        intent_id=intent_id,
        user_id=user_id,
        package_id=package_id,
        package_name=package_name,
        credits_amount=credits_amount,
        price_cents=price_cents,
        currency=currency,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
    )


__all__ = [
    "StripeProvider",
    "StripeSessionResult",
    "create_stripe_checkout_session",
]
