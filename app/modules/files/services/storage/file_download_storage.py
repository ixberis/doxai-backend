
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/file_download_storage.py

Descarga de archivos desde Supabase Storage (o cliente HTTP equivalente).

Compat y contratos esperados por tests:
- Clase `FileDownloadStorage` con método `download(storage_path) -> bytes`.
- Función helper `download_file_from_project(storage_path) -> bytes`
  (usada por otros servicios y tests).

Autor: Ixchel Beristain
Actualizado: 02/11/2025
"""

from __future__ import annotations

from typing import Optional, Protocol, Any

from app.shared.config import settings
from app.shared.utils.http_storage_client import get_http_storage_client


class _HttpStorageClient(Protocol):
    async def download_file(self, bucket: str, storage_path: str) -> Any: ...


class FileDownloadStorage:
    def __init__(
        self,
        client: Optional[_HttpStorageClient] = None,
        bucket: Optional[str] = None,
        paths_service: Optional[Any] = None,
        gateway: Optional[Any] = None,
        **kwargs
    ) -> None:
        # Priorizar gateway sobre client (para tests)
        self.gateway = gateway
        self.client = gateway or client or get_http_storage_client()
        self.bucket = bucket or settings.supabase_bucket_name
        self.paths_service = paths_service

    async def download(self, storage_path: str) -> bytes:
        """Descarga archivo y retorna bytes."""
        if self._is_unsafe_path(storage_path):
            raise ValueError(f"Ruta insegura: {storage_path}")
        
        # Si hay gateway (tests), usar su método download
        if self.gateway and hasattr(self.gateway, 'download'):
            return await self.gateway.download(storage_path)
        
        blob = await self.client.download_file(self.bucket, storage_path)
        # Algunos clientes devuelven {"content": bytes, ...}
        if isinstance(blob, dict):
            return blob.get("content", b"")
        return blob  # asumimos bytes

    async def download_stream(self, storage_path: str):
        """Descarga archivo como stream file-like."""
        if self._is_unsafe_path(storage_path):
            raise ValueError(f"Ruta insegura: {storage_path}")
        from io import BytesIO
        data = await self.download(storage_path)
        stream = BytesIO(data)
        # Agregar método read async para compatibilidad
        async def async_read():
            return data
        stream.read = async_read
        return stream

    async def download_with_metadata(self, storage_path: str) -> dict:
        """Descarga archivo con metadatos adicionales."""
        if self._is_unsafe_path(storage_path):
            raise ValueError(f"Ruta insegura: {storage_path}")
        data = await self.download(storage_path)
        return {
            "path": storage_path,
            "size": len(data),
            "bytes": data,
        }

    def _is_unsafe_path(self, path: str) -> bool:
        """Valida que la ruta sea segura (no traversal)."""
        if not path or not isinstance(path, str):
            return True
        if path.startswith("/") or ".." in path:
            return True
        return False


# --------- Helper de compatibilidad (usado en otros módulos/tests) ---------

async def download_file_from_project(storage_path: str) -> bytes:
    storage = FileDownloadStorage()
    return await storage.download(storage_path)

# Fin de archivo backend/app/services/storage/file_download_storage.py







