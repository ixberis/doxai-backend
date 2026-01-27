# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/billing/files_billing_service.py

Servicio de billing para el módulo Files.

Responsabilidades:
- Calcular créditos a consumir por tamaño de archivo
- Consumir créditos con module='files' para métricas de Admin
- Verificar saldo disponible antes de operaciones costosas

Fórmula de cobro (configurable):
- BASE_CREDITS: costo fijo por archivo (default: 1)
- CREDITS_PER_MB: costo adicional por cada MB (default: 1)
- MIN_CREDITS: mínimo a cobrar (default: 1)
- MAX_CREDITS: máximo a cobrar por archivo (default: 50)

Ejemplo:
- Archivo de 5 MB → 1 + 5 = 6 créditos
- Archivo de 100 KB → 1 + 0 = 1 crédito (mínimo)
- Archivo de 100 MB → min(1 + 100, 50) = 50 créditos (cap)

Autor: DoxAI
Fecha: 2026-01-26
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.credits.services import WalletService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilesBillingConfig:
    """Configuración de billing para Files."""
    
    # Costo fijo por archivo
    base_credits: int = 1
    
    # Costo adicional por MB
    credits_per_mb: float = 1.0
    
    # Mínimo a cobrar
    min_credits: int = 1
    
    # Máximo a cobrar (cap)
    max_credits: int = 50
    
    @classmethod
    def from_env(cls) -> "FilesBillingConfig":
        """Carga configuración desde variables de entorno."""
        return cls(
            base_credits=int(os.getenv("FILES_BILLING_BASE_CREDITS", "1")),
            credits_per_mb=float(os.getenv("FILES_BILLING_CREDITS_PER_MB", "1.0")),
            min_credits=int(os.getenv("FILES_BILLING_MIN_CREDITS", "1")),
            max_credits=int(os.getenv("FILES_BILLING_MAX_CREDITS", "50")),
        )


def calculate_credits_for_file(
    file_size_bytes: int,
    config: Optional[FilesBillingConfig] = None,
) -> int:
    """
    Calcula los créditos a consumir por un archivo.
    
    Args:
        file_size_bytes: Tamaño del archivo en bytes
        config: Configuración de billing (usa default si None)
        
    Returns:
        Número de créditos a consumir (int >= min_credits, <= max_credits)
    """
    if config is None:
        config = FilesBillingConfig()
    
    # Convertir a MB
    size_mb = file_size_bytes / (1024 * 1024)
    
    # Calcular costo: base + por MB
    raw_credits = config.base_credits + (size_mb * config.credits_per_mb)
    
    # Aplicar bounds
    credits = max(config.min_credits, min(int(raw_credits), config.max_credits))
    
    return credits


class FilesBillingService:
    """
    Servicio para consumo de créditos por operaciones Files.
    
    Uso:
        service = FilesBillingService()
        await service.charge_product_file_creation(
            session=db,
            auth_user_id=user_id,
            file_size_bytes=len(file_bytes),
            file_name="document.pdf",
            product_file_id=pf_id,
        )
    """
    
    MODULE_NAME = "files"
    
    def __init__(
        self,
        wallet_service: Optional[WalletService] = None,
        config: Optional[FilesBillingConfig] = None,
    ):
        self.wallet_service = wallet_service or WalletService()
        self.config = config or FilesBillingConfig.from_env()
    
    def calculate_credits(self, file_size_bytes: int) -> int:
        """Calcula créditos para un archivo dado su tamaño."""
        return calculate_credits_for_file(file_size_bytes, self.config)
    
    async def check_sufficient_balance(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
        file_size_bytes: int,
    ) -> tuple[bool, int, int]:
        """
        Verifica si el usuario tiene saldo suficiente.
        
        Returns:
            Tuple de (has_enough, available, required)
        """
        required = self.calculate_credits(file_size_bytes)
        available = await self.wallet_service.get_available(session, auth_user_id)
        
        return (available >= required, available, required)
    
    async def charge_product_file_creation(
        self,
        session: AsyncSession,
        *,
        auth_user_id: UUID,
        file_size_bytes: int,
        file_name: str,
        product_file_id: UUID,
        idempotency_key: Optional[str] = None,
    ) -> int:
        """
        Cobra créditos por la creación de un archivo producto.
        
        Args:
            session: AsyncSession de DB
            auth_user_id: UUID del usuario (SSOT)
            file_size_bytes: Tamaño del archivo en bytes
            file_name: Nombre del archivo (para descripción)
            product_file_id: UUID del ProductFile creado
            idempotency_key: Clave de idempotencia (opcional)
            
        Returns:
            Número de créditos consumidos
            
        Raises:
            ValueError: Si saldo insuficiente
        """
        credits = self.calculate_credits(file_size_bytes)
        
        # Generar idempotency key si no se proporciona
        if idempotency_key is None:
            idempotency_key = f"files_product_{product_file_id}"
        
        # Descripción legible
        size_kb = file_size_bytes / 1024
        if size_kb < 1024:
            size_str = f"{size_kb:.1f} KB"
        else:
            size_str = f"{size_kb / 1024:.2f} MB"
        
        description = f"Generación de archivo: {file_name} ({size_str})"
        
        logger.info(
            "[files_billing] Charging credits: auth_user_id=%s credits=%d file=%s size=%s",
            str(auth_user_id)[:8] + "...",
            credits,
            file_name[:30],
            size_str,
        )
        
        await self.wallet_service.deduct_credits(
            session,
            auth_user_id,
            credits,
            operation_code="FILE_PRODUCT_GENERATION",
            description=description,
            idempotency_key=idempotency_key,
            job_id=str(product_file_id),
            tx_metadata={
                "type": "product_file_creation",
                "product_file_id": str(product_file_id),
                "file_name": file_name,
                "file_size_bytes": file_size_bytes,
            },
            module=self.MODULE_NAME,  # ← SSOT: etiqueta para métricas
        )
        
        logger.info(
            "[files_billing] Credits charged successfully: auth_user_id=%s credits=%d product_file_id=%s",
            str(auth_user_id)[:8] + "...",
            credits,
            str(product_file_id)[:8] + "...",
        )
        
        return credits


# Singleton para uso directo (opcional)
_default_service: Optional[FilesBillingService] = None


def get_files_billing_service() -> FilesBillingService:
    """Obtiene la instancia default del servicio."""
    global _default_service
    if _default_service is None:
        _default_service = FilesBillingService()
    return _default_service


__all__ = [
    "FilesBillingService",
    "FilesBillingConfig",
    "calculate_credits_for_file",
    "get_files_billing_service",
]
