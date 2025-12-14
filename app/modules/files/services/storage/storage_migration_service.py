
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/storage_migration_service.py

Servicio de migración simple entre "backends" lógicos de storage.
Los tests típicamente esperan una clase `StorageMigrationService` con
un método `migrate(prefix, list_fn, reader_fn, writer_fn, delete_src)` o similar.
Aquí dejamos una versión flexible.

Autor: DoxAI
Actualizado: 2025-11-01
"""

from __future__ import annotations
from typing import Callable, Iterable, Awaitable, Optional, List, Any
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import StorageBackend


class StorageMigrationService:
    """
    Servicio para migrar archivos entre backends de storage.
    
    Acepta dos firmas de constructor:
    1. Nueva (para tests): StorageMigrationService(db, src_gateway, dst_gateway)
    2. Legacy: StorageMigrationService(list_fn, read_fn, write_fn, delete_fn)
    """

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        src_gateway: Optional[Any] = None,
        dst_gateway: Optional[Any] = None,
        list_fn: Optional[Callable[[str], Awaitable[Iterable[str]]]] = None,
        read_fn: Optional[Callable[[str], Awaitable[bytes]]] = None,
        write_fn: Optional[Callable[[str, bytes], Awaitable[None]]] = None,
        delete_fn: Optional[Callable[[str], Awaitable[None]]] = None,
        **kwargs
    ) -> None:
        # Modo nuevo (tests con gateways)
        if db is not None and src_gateway is not None and dst_gateway is not None:
            self.db = db
            self.src_gateway = src_gateway
            self.dst_gateway = dst_gateway
            self.mode = "gateway"
        # Modo legacy (funciones)
        elif list_fn is not None and read_fn is not None and write_fn is not None:
            self.list_fn = list_fn
            self.read_fn = read_fn
            self.write_fn = write_fn
            self.delete_fn = delete_fn
            self.mode = "functions"
        else:
            raise ValueError("Constructor requiere (db, src_gateway, dst_gateway) o (list_fn, read_fn, write_fn)")

    async def migrate_file(self, file_id: int, new_backend: Any) -> InputFile:
        """
        Migra un archivo específico a un nuevo backend (modo gateway).
        """
        if self.mode != "gateway":
            raise RuntimeError("migrate_file requiere modo gateway")
        
        # Validar backend
        if isinstance(new_backend, str):
            try:
                new_backend = StorageBackend(new_backend)
            except ValueError:
                raise ValueError(f"Backend inválido: {new_backend}")
        
        # Obtener archivo
        file = await self.db.get(InputFile, file_id)
        if not file:
            raise ValueError(f"Archivo no encontrado: {file_id}")
        
        path = file.input_file_storage_path
        
        # Descargar de origen
        data = await self.src_gateway.download(path)
        
        # Subir a destino
        await self.dst_gateway.upload(path, data)
        
        # Actualizar BD
        file.input_file_storage_backend = new_backend
        await self.db.flush()
        
        # Eliminar de origen
        await self.src_gateway.delete(path)
        
        return file

    async def migrate(self, prefix: str, *, delete_source: bool = False) -> List[str]:
        """
        Migración masiva por prefijo (modo legacy con funciones).
        """
        if self.mode != "functions":
            raise RuntimeError("migrate requiere modo functions")
        
        paths = list(await self.list_fn(prefix))
        copied: List[str] = []

        async def _one(p: str) -> None:
            data = await self.read_fn(p)
            await self.write_fn(p, data)
            if delete_source and self.delete_fn is not None:
                await self.delete_fn(p)
            copied.append(p)

        await asyncio.gather(*[ _one(p) for p in paths ])
        return copied

# Fin del archivo backend\app\modules\files\services\storage\storage_migration_service.py







