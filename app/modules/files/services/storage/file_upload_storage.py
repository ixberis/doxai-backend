
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/file_upload_storage.py

Subida de archivos a Storage.

Compat y contratos esperados por tests:
- Clase `FileUploadStorage` con método
  `upload(storage_path, content: bytes, mime_type: str, overwrite=False) -> None`.
- Función helper `upload_file_to_project(storage_path, content, mime_type, overwrite=False)`.

Autor: Ixchel Beristain
Actualizado: 04/11/2025
"""

from __future__ import annotations

from typing import Optional, Protocol, Any

from app.shared.config import settings
from app.shared.utils.http_storage_client import get_http_storage_client


class _HttpStorageClient(Protocol):
    async def upload_file(self, bucket: str, storage_path: str, content: bytes, mime_type: str, overwrite: bool = False) -> None: ...


class FileUploadStorage:
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

    async def upload(self, storage_path: str, content: bytes, mime_type: str, overwrite: bool = False) -> None:
        await self.client.upload_file(self.bucket, storage_path, content, mime_type, overwrite=overwrite)

    async def upload_input_file(
        self,
        user_id: str,
        project_id: int,
        file_name: str,
        data: Any,
        content_type: str = "application/octet-stream",
    ) -> Any:
        """Sube archivo input con validación y construcción de ruta."""
        from app.modules.files.facades.errors import StoragePathCollision
        import io
        
        # Validar nombre de archivo
        if not file_name or not isinstance(file_name, str):
            raise ValueError("file_name inválido")
        if "../" in file_name or "\\" in file_name:
            raise ValueError(f"Nombre de archivo inseguro: {file_name}")
        
        # Construir ruta
        if self.paths_service:
            storage_path = self.paths_service.generate_input_file_path(
                user_id=user_id, project_id=project_id, file_name=file_name
            )
        else:
            storage_path = f"users/{user_id}/projects/{project_id}/input/{file_name}"
        
        # Convertir stream a bytes si es necesario
        if hasattr(data, 'read'):
            if hasattr(data, 'seek'):
                data.seek(0)
            content = data.read()
        else:
            content = data
        
        # Verificar colisión (simular con gateway fake)
        if hasattr(self, 'gateway'):
            if await self.gateway.exists(storage_path):
                raise StoragePathCollision(f"Ruta ya existente: {storage_path}")
            result = await self.gateway.upload(storage_path, content, content_type=content_type)
        else:
            await self.upload(storage_path, content, content_type)
            result = {
                "path": storage_path,
                "size": len(content),
                "content_type": content_type,
            }
        
        # Retornar objeto con atributos
        class UploadResult:
            def __init__(self, path, size, content_type):
                self.path = path
                self.size = size
                self.content_type = content_type
        
        return UploadResult(
            path=result.get("path", storage_path),
            size=result.get("size", len(content)),
            content_type=result.get("content_type", content_type),
        )


# --------- Helper de compatibilidad ---------

async def upload_file_to_project(storage_path: str, content: bytes, mime_type: str, overwrite: bool = False) -> None:
    svc = FileUploadStorage()
    await svc.upload(storage_path, content, mime_type, overwrite=overwrite)

# Fin del archivo backend\app\modules\files\services\storage\file_upload_storage.py






