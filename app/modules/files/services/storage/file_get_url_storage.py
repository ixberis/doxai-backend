
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/file_get_url_storage.py

Obtención de URLs (públicas o firmadas) para un archivo en Storage.

Compat y contratos esperados por tests:
- Clase `FileGetUrlStorage` con método `get_url(storage_path, expires_in=None) -> str`.
- Función helper `get_public_url(storage_path, expires_in=None) -> str`.
- **Nuevo**: `get_download_url(storage_path, expires_in=None) -> str` (alias usado por servicios).

Autor: Ixchel Beristain
Actualizado: 04/11/2025
"""

from __future__ import annotations

from typing import Optional, Protocol, Any

from app.shared.config import settings
from app.shared.utils.http_storage_client import get_http_storage_client

class _HttpStorageClient(Protocol):
    async def get_public_url(self, bucket: str, storage_path: str) -> str: ...
    async def get_signed_url(self, bucket: str, storage_path: str, expires_in: int) -> str: ...


class FileGetUrlStorage:
    def __init__(
        self,
        client: Optional[_HttpStorageClient] = None,
        bucket: Optional[str] = None,
        paths_service: Optional[Any] = None,
        gateway: Optional[Any] = None,
        **kwargs
    ) -> None:
        self.gateway = gateway
        self.client = gateway or client or get_http_storage_client()
        self.bucket = bucket or settings.supabase_bucket_name
        self.paths_service = paths_service

    async def get_url(self, storage_path: str, *, expires_in: Optional[int] = None) -> str:
        if expires_in is None or expires_in <= 0:
            return await self.client.get_public_url(self.bucket, storage_path)
        return await self.client.get_signed_url(self.bucket, storage_path, expires_in)

    async def get_presigned_url(self, storage_path: str, expires_in: Any = 3600) -> str:
        """Genera URL presignada con validación."""
        from datetime import timedelta
        
        # Validar ruta
        if not storage_path or not isinstance(storage_path, str):
            raise ValueError("storage_path inválido")
        if storage_path.startswith("/") or "../" in storage_path:
            raise ValueError(f"Ruta insegura: {storage_path}")
        
        # Normalizar expires_in
        if isinstance(expires_in, timedelta):
            expires_in = int(expires_in.total_seconds())
        else:
            expires_in = int(expires_in)
        
        if expires_in <= 0:
            raise ValueError("expires_in debe ser positivo")
        
        # Delegar al gateway o cliente
        if hasattr(self, 'gateway'):
            return await self.gateway.presign_url(storage_path, expires_in)
        else:
            return await self.get_url(storage_path, expires_in=expires_in)


# --------- Helpers de compatibilidad ---------

async def get_public_url(storage_path: str, expires_in: Optional[int] = None) -> str:
    svc = FileGetUrlStorage()
    return await svc.get_url(storage_path, expires_in=expires_in)


async def get_download_url(storage_path: str, expires_in: Optional[int] = None) -> str:
    """
    Alias común en servicios legacy. Delegamos a get_public_url/get_url.
    """
    return await get_public_url(storage_path, expires_in=expires_in)

# Fin del archivo backend/app/services/storage/file_get_url_storage.py







