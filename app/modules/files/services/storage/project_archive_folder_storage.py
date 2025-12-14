
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/project_archive_folder_storage.py

Mueve toda la carpeta de un proyecto a una ubicación de archivo lógico en Supabase Storage:
de: user_id/slug/
a:   user_id/archivados/slug/

Autor: DoxAI
Actualizado: 02/11/2025
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List
from app.shared.config import settings
from app.shared.utils.http_storage_client import get_http_storage_client

logger = logging.getLogger(__name__)


async def _list_all_under(prefix: str) -> List[Dict[str, Any]]:
    """Lista todos los objetos bajo un prefijo (sin paginación compleja)."""
    client = get_http_storage_client()
    resp = await client.list_files(
        bucket=settings.supabase_bucket_name,
        prefix=prefix,
        limit=1000,
        offset=0,
    )
    return resp["files"] if isinstance(resp, dict) else (resp or [])


async def archive_project_folder(user_id: str, slug: str) -> bool:
    """
    Copia todo <user_id>/<slug>/* a <user_id>/archivados/<slug>/* y elimina los originales.
    """
    if not user_id or not slug:
        raise ValueError("user_id y slug son obligatorios")

    client = get_http_storage_client()
    source_prefix = f"{user_id}/{slug}/"
    target_prefix = f"{user_id}/archivados/{slug}/"

    items = await _list_all_under(source_prefix)
    if not items:
        logger.info("No hay archivos para archivar en %s", source_prefix)
        return False

    moved = 0
    for it in items:
        name = it.get("name")
        if not name or name.endswith("/"):
            continue

        old_path = f"{source_prefix}{name}"
        new_path = f"{target_prefix}{name}"

        try:
            dl = await client.download_file(settings.supabase_bucket_name, old_path)
            content = dl["content"] if isinstance(dl, dict) else dl
            await client.upload_file(
                bucket=settings.supabase_bucket_name,
                path=new_path,
                file_data=content,
                content_type="application/octet-stream",
                overwrite=True,
            )
            await client.delete_file(settings.supabase_bucket_name, old_path)
            moved += 1
            logger.info("📦 %s → %s", old_path, new_path)
        except Exception as e:
            logger.warning("No se pudo mover %s: %s", old_path, e)

    return moved > 0

# Fin del archivo backend\app\modules\files\services\storage\project_archive_folder_storage.py







