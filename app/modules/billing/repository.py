# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/repository.py

Repositorio para checkout_intents con manejo de idempotencia y concurrencia.

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CheckoutIntent, CheckoutIntentStatus

logger = logging.getLogger(__name__)


class CheckoutIntentRepository:
    """
    Repositorio para operaciones con checkout_intents.
    
    Maneja idempotencia y concurrencia de forma segura.
    """
    
    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        user_id: int,
        idempotency_key: str,
    ) -> Optional[CheckoutIntent]:
        """
        Busca un checkout intent por user_id + idempotency_key.
        
        Args:
            session: Sesión de base de datos
            user_id: ID del usuario
            idempotency_key: Clave idempotente
            
        Returns:
            CheckoutIntent si existe, None si no
        """
        stmt = select(CheckoutIntent).where(
            CheckoutIntent.user_id == user_id,
            CheckoutIntent.idempotency_key == idempotency_key,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        package_id: str,
        idempotency_key: str,
        credits_amount: int,
        price_cents: int,
        currency: str,
        checkout_url: Optional[str] = None,
        status: str = CheckoutIntentStatus.CREATED.value,
        provider: Optional[str] = None,
    ) -> CheckoutIntent:
        """
        Crea un nuevo checkout intent.
        
        Args:
            session: Sesión de base de datos
            user_id: ID del usuario
            package_id: ID del paquete de créditos
            idempotency_key: Clave idempotente
            credits_amount: Créditos del paquete
            price_cents: Precio en centavos
            currency: Moneda (ISO 4217)
            checkout_url: URL de checkout (opcional)
            status: Estado inicial
            provider: Proveedor de pago (opcional)
            
        Returns:
            CheckoutIntent creado
        """
        intent = CheckoutIntent(
            user_id=user_id,
            package_id=package_id,
            idempotency_key=idempotency_key,
            credits_amount=credits_amount,
            price_cents=price_cents,
            currency=currency,
            checkout_url=checkout_url,
            status=status,
            provider=provider,
        )
        session.add(intent)
        await session.flush()
        return intent
    
    async def create_or_get_existing(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        package_id: str,
        idempotency_key: str,
        credits_amount: int,
        price_cents: int,
        currency: str,
        checkout_url: Optional[str] = None,
        status: str = CheckoutIntentStatus.CREATED.value,
        provider: Optional[str] = None,
    ) -> tuple[CheckoutIntent, bool]:
        """
        Crea un nuevo intent o retorna el existente si hay conflicto de idempotencia.
        
        Maneja IntegrityError por unique constraint de forma segura.
        
        Args:
            session: Sesión de base de datos
            user_id: ID del usuario
            package_id: ID del paquete
            idempotency_key: Clave idempotente
            credits_amount: Créditos del paquete
            price_cents: Precio en centavos
            currency: Moneda
            checkout_url: URL de checkout
            status: Estado inicial
            provider: Proveedor de pago
            
        Returns:
            Tuple de (CheckoutIntent, created: bool)
            - Si created=True, es un nuevo intent
            - Si created=False, es un intent existente (idempotencia)
        """
        try:
            intent = await self.create(
                session,
                user_id=user_id,
                package_id=package_id,
                idempotency_key=idempotency_key,
                credits_amount=credits_amount,
                price_cents=price_cents,
                currency=currency,
                checkout_url=checkout_url,
                status=status,
                provider=provider,
            )
            return intent, True
            
        except IntegrityError as e:
            # Conflicto de unique constraint - rollback y re-fetch
            logger.info(
                "Idempotency conflict for user=%s key=%s, fetching existing",
                user_id,
                idempotency_key[:8] + "...",
            )
            await session.rollback()
            
            existing = await self.get_by_idempotency_key(
                session,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            
            if existing is None:
                # No debería pasar, pero por seguridad re-raise
                logger.error(
                    "IntegrityError but no existing intent found: %s",
                    e,
                )
                raise
            
            return existing, False
    
    async def get_by_id(
        self,
        session: AsyncSession,
        intent_id: int,
    ) -> Optional[CheckoutIntent]:
        """
        Busca un checkout intent por ID.
        
        Args:
            session: Sesión de base de datos
            intent_id: ID del intent
            
        Returns:
            CheckoutIntent si existe, None si no
        """
        return await session.get(CheckoutIntent, intent_id)
    
    async def update_status(
        self,
        session: AsyncSession,
        intent_id: int,
        new_status: CheckoutIntentStatus,
    ) -> Optional[CheckoutIntent]:
        """
        Actualiza el estado de un intent.
        
        Args:
            session: Sesión de base de datos
            intent_id: ID del intent
            new_status: Nuevo estado
            
        Returns:
            CheckoutIntent actualizado, o None si no existe
        """
        intent = await self.get_by_id(session, intent_id)
        if intent is None:
            return None
        
        intent.status = new_status.value
        await session.flush()
        return intent


__all__ = ["CheckoutIntentRepository"]
