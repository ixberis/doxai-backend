
# -*- coding: utf-8 -*-
"""
Repositorio para la tabla wallets.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.models.wallet_models import Wallet


class WalletRepository(BaseRepository[Wallet]):
    def __init__(self):
        super().__init__(Wallet)

    # -----------------------------------------------------------
    # Obtener wallet por user_id (única en el sistema)
    # -----------------------------------------------------------
    async def get_by_user_id(
        self, session: AsyncSession, user_id: str
    ) -> Optional[Wallet]:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Verificar existencia
    # -----------------------------------------------------------
    async def exists(self, session: AsyncSession, user_id: str) -> bool:
        return (await self.get_by_user_id(session, user_id)) is not None
    
# Fin del archivo backend\app\modules\payments\repositories\wallet_repository.py