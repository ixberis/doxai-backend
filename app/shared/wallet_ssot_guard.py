# -*- coding: utf-8 -*-
"""
backend/app/shared/wallet_ssot_guard.py

Fail-fast guard para verificar que Wallet apunta a la tabla correcta.

Uso:
    from app.shared.wallet_ssot_guard import assert_wallet_ssot

    # En get_credits_balance o similar:
    assert_wallet_ssot(Wallet)  # Lanza RuntimeError si SSOT inválido

Habilitado con: STRICT_WALLET_SSOT=1

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_STRICT_MODE = os.getenv("STRICT_WALLET_SSOT", "0") == "1"
_ALREADY_VALIDATED = False


class WalletSSOTError(RuntimeError):
    """Error cuando el modelo Wallet no apunta a la tabla SSOT correcta."""
    pass


def assert_wallet_ssot(wallet_class: Any) -> None:
    """
    Valida que el modelo Wallet apunta a 'wallets' (no 'payments_wallet').
    
    Validaciones:
    1. wallet_class.__tablename__ == "wallets"
    2. wallet_class.__table__.name == "wallets" (si existe __table__)
    3. wallet_class.__table__.fullname NO contiene "payments_wallet"
    
    Si STRICT_WALLET_SSOT=1 y la validación falla:
    - Loguea ERROR con detalles completos del modelo
    - Lanza WalletSSOTError
    
    Si STRICT_WALLET_SSOT=0 (default):
    - Solo loguea WARNING y continúa
    
    Args:
        wallet_class: Clase del modelo Wallet
        
    Raises:
        WalletSSOTError: Si SSOT inválido y modo estricto activo
    """
    global _ALREADY_VALIDATED
    
    # Extraer metadatos del modelo
    tablename = getattr(wallet_class, "__tablename__", "UNKNOWN")
    module = getattr(wallet_class, "__module__", "UNKNOWN")
    
    # Extraer __table__ metadata (si existe, modelo ya compilado por SQLAlchemy)
    table_name: str | None = None
    table_fullname: str | None = None
    if hasattr(wallet_class, "__table__"):
        table_obj = wallet_class.__table__
        table_name = getattr(table_obj, "name", None)
        table_fullname = str(table_obj.fullname) if hasattr(table_obj, "fullname") else None
    
    # Validaciones SSOT (todas deben pasar)
    errors: list[str] = []
    
    # 1. __tablename__ debe ser "wallets"
    if tablename != "wallets":
        errors.append(f"__tablename__='{tablename}' (expected 'wallets')")
    
    # 2. __table__.name debe ser "wallets" (si existe)
    if table_name is not None and table_name != "wallets":
        errors.append(f"__table__.name='{table_name}' (expected 'wallets')")
    
    # 3. __table__.fullname NO debe contener "payments_wallet"
    if table_fullname is not None and "payments_wallet" in table_fullname.lower():
        errors.append(f"__table__.fullname='{table_fullname}' contains 'payments_wallet'")
    
    is_valid = len(errors) == 0
    
    if not is_valid:
        error_detail = " | ".join(errors)
        error_msg = (
            f"[WALLET_SSOT_VIOLATION] {error_detail} | "
            f"module={module} | "
            f"table_name={table_name} | "
            f"table_fullname={table_fullname}"
        )
        
        if _STRICT_MODE:
            logger.error(error_msg)
            raise WalletSSOTError(error_msg)
        else:
            # Solo loguear una vez para no spamear
            if not _ALREADY_VALIDATED:
                logger.warning(error_msg + " | STRICT_WALLET_SSOT=0, continuing anyway")
    else:
        # Log una vez que está correcto (solo primera vez)
        if not _ALREADY_VALIDATED:
            logger.debug(
                f"[wallet_ssot] OK: tablename={tablename}, "
                f"table_name={table_name}, table_fullname={table_fullname}, "
                f"module={module}"
            )
    
    _ALREADY_VALIDATED = True


def is_strict_mode() -> bool:
    """Retorna True si STRICT_WALLET_SSOT=1."""
    return _STRICT_MODE


__all__ = ["assert_wallet_ssot", "WalletSSOTError", "is_strict_mode"]
