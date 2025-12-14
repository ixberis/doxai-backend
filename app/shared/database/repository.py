
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/repository.py

Repositorio base para operaciones async con SQLAlchemy.

Autor: DoxAI (adaptado para Payments)
Fecha: 2025-11-20
"""

from typing import Any, Type, TypeVar, Generic, Sequence, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")  # modelo ORM


class BaseRepository(Generic[T]):
    """Repositorio asincrónico base para CRUD común."""

    def __init__(self, model: Type[T]):
        self.model = model

    # -------------------------------------------------------------
    # CRUD básico
    # -------------------------------------------------------------
    async def get(self, session: AsyncSession, obj_id: Any) -> Optional[T]:
        return await session.get(self.model, obj_id)

    async def list(self, session: AsyncSession) -> Sequence[T]:
        result = await session.execute(select(self.model))
        return result.scalars().all()

    async def create(self, session: AsyncSession, **kwargs) -> T:
        obj = self.model(**kwargs)
        session.add(obj)
        await session.flush()
        return obj

    async def delete(self, session: AsyncSession, obj: T) -> None:
        await session.delete(obj)
        await session.flush()

# Fin del archivo backend\app\shared\database\repository.py