# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage_ops_service.py

Servicio de alto nivel para operaciones de storage.
Define AsyncStorageClient como protocolo y funciones helper.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class AsyncStorageClient(Protocol):
    """
    Protocolo que define la interfaz de un cliente de storage asíncrono.
    
    Usado por facades para interactuar con backends de storage (Supabase, S3, etc.)
    sin acoplarse a una implementación concreta.
    """

    async def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        mime_type: str | None = None,
    ) -> None:
        """Sube bytes al storage en la ruta especificada."""
        ...

    async def get_download_url(
        self,
        bucket: str,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Genera una URL de descarga temporal firmada."""
        ...

    async def delete_object(
        self,
        bucket: str,
        key: str,
    ) -> None:
        """Elimina un objeto del storage."""
        ...


# --- Funciones helper que usan AsyncStorageClient ---

async def upload_file_bytes(
    storage_client: AsyncStorageClient,
    *,
    bucket: str,
    key: str,
    data: bytes,
    mime_type: str | None = None,
) -> None:
    """
    Sube bytes a storage usando el cliente proporcionado.
    
    Args:
        storage_client: Cliente de storage que implementa AsyncStorageClient
        bucket: Nombre del bucket
        key: Ruta/clave del archivo en el storage
        data: Bytes del archivo
        mime_type: Tipo MIME del archivo (opcional)
    """
    await storage_client.upload_bytes(
        bucket=bucket,
        key=key,
        data=data,
        mime_type=mime_type,
    )


async def generate_download_url(
    storage_client: AsyncStorageClient,
    *,
    bucket: str,
    key: str,
    expires_in_seconds: int = 3600,
) -> str:
    """
    Genera una URL de descarga temporal para un archivo.
    
    Args:
        storage_client: Cliente de storage que implementa AsyncStorageClient
        bucket: Nombre del bucket
        key: Ruta/clave del archivo en el storage
        expires_in_seconds: Tiempo de validez de la URL en segundos
        
    Returns:
        URL firmada temporal para descargar el archivo
    """
    return await storage_client.get_download_url(
        bucket=bucket,
        key=key,
        expires_in_seconds=expires_in_seconds,
    )


async def delete_file_from_storage(
    storage_client: AsyncStorageClient,
    *,
    bucket: str,
    key: str,
) -> None:
    """
    Elimina un archivo del storage.
    
    Args:
        storage_client: Cliente de storage que implementa AsyncStorageClient
        bucket: Nombre del bucket
        key: Ruta/clave del archivo a eliminar
    """
    await storage_client.delete_object(bucket=bucket, key=key)


class StorageOpsService:
    """Servicio para operaciones de storage."""

    def __init__(self, storage):
        self.storage = storage

    async def list_files(
        self,
        path: str,
        recursive: bool = False,
        prefix: Optional[str] = None,
    ) -> List[dict]:
        """
        Lista archivos en el storage.
        
        Args:
            path: Ruta base
            recursive: Búsqueda recursiva
            prefix: Filtro por prefijo
            
        Returns:
            Lista de diccionarios con información de archivos
        """
        return await self.storage.list(path=path, recursive=recursive, prefix=prefix)

    async def delete_file(self, path: str) -> bool:
        """
        Elimina un archivo del storage.
        
        Args:
            path: Ruta del archivo
            
        Returns:
            True si se eliminó correctamente
            
        Raises:
            FileNotFoundError: Si el archivo no existe
        """
        return await self.storage.delete(path)

    async def move_file(self, src: str, dest: str) -> bool:
        """
        Mueve un archivo a nueva ubicación.
        
        Args:
            src: Ruta origen
            dest: Ruta destino
            
        Returns:
            True si se movió correctamente
            
        Raises:
            FileNotFoundError: Si el archivo origen no existe
            ValueError: Si la ruta de destino es inválida
        """
        return await self.storage.move(src, dest)


__all__ = [
    "AsyncStorageClient",
    "StorageOpsService",
    "upload_file_bytes",
    "generate_download_url",
    "delete_file_from_storage",
]
