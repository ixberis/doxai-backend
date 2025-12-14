
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/file_list_storage.py

Servicio de listado de archivos en storage con filtros y paginación.

Autor: Ixchel Beristain
Fecha: 04/11/2025
"""

from typing import Any, Optional


class FileListStorage:
    def __init__(self, paths_service=None, gateway=None, *args, **kwargs) -> None:
        self.paths_service = paths_service
        self.gateway = gateway

    async def list_folder(
        self,
        base: str,
        *,
        recursive: bool = False,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        limit: Optional[int] = None,
        token: Optional[str] = None,
    ) -> Any:
        """
        Lista archivos en una carpeta con filtros opcionales.
        
        Retorna dict con 'items' y opcionalmente 'next_token' o lista directa.
        """
        # Validar ruta segura
        if "../" in base or base.startswith("/"):
            raise ValueError("Invalid path")
        
        if not self.gateway:
            return []
        
        # Obtener items del gateway
        items = await self.gateway.list(base, recursive=recursive)
        
        # Convertir a lista si es necesario
        if isinstance(items, dict):
            items = items.get("items", [])
        
        # Aplicar filtros
        if prefix:
            items = [i for i in items if prefix in i["path"]]
        
        if suffix:
            items = [i for i in items if i["path"].endswith(suffix)]
        
        # Aplicar paginación si se solicita
        if limit is not None:
            items = items[:limit]
        
        return {"items": items}


__all__ = ["FileListStorage"]

# Fin del archivo backend/app/modules/files/services/storage/file_list_storage.py
