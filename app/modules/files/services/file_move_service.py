# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/file_move_service.py

Servicio para mover archivos en el storage y actualizar la base de datos.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.facades.errors import StoragePathCollision
from app.modules.files.models.input_file_models import InputFile


class FileMoveService:
    """Servicio para movimiento de archivos."""

    def __init__(self, db: AsyncSession, storage):
        self.db = db
        self.storage = storage

    async def move_file(self, file_id: UUID, new_path: str) -> InputFile:
        """
        Mueve un archivo a una nueva ruta.
        
        Args:
            file_id: ID del archivo
            new_path: Nueva ruta de almacenamiento
            
        Returns:
            Archivo actualizado
            
        Raises:
            ValueError: Si el archivo no existe o la ruta es inválida
            StoragePathCollision: Si la ruta de destino ya existe
            IOError: Si falla la operación de storage
        """
        # Validar ruta
        if "../" in new_path or new_path.startswith("/"):
            raise ValueError("Invalid path")

        # Buscar archivo
        stmt = select(InputFile).where(InputFile.input_file_id == file_id)
        result = await self.db.execute(stmt)
        file = result.scalar_one_or_none()

        if not file:
            raise ValueError(f"File not found: {file_id}")

        old_path = file.input_file_storage_path

        try:
            # Mover en storage
            await self.storage.move(old_path, new_path)

            # Actualizar BD
            file.input_file_storage_path = new_path
            await self.db.commit()
            await self.db.refresh(file)

            return file

        except StoragePathCollision:
            # Rollback y propagar
            await self.db.rollback()
            raise

        except Exception as e:
            # Rollback en cualquier error
            await self.db.rollback()
            raise


__all__ = ["FileMoveService"]
