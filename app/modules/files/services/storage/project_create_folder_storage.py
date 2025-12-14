
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/project_create_folder_storage.py

Crea user_id/slug/input_files/.keep y user_id/slug/product_files/.keep
para simular directorios en Storage.

Autor: Ixchel Beristain 
Actualizado: 02/11/2025
"""

from __future__ import annotations

import logging
from app.shared.utils.http_storage_client import get_http_storage_client
from app.shared.config import settings

logger = logging.getLogger(__name__)


async def create_project_storage_folders(user_id: str, slug: str) -> bool:
    if not user_id or not slug:
        logger.warning("create_project_storage_folders: parámetros inválidos")
        return False

    client = get_http_storage_client()
    base = f"{user_id}/{slug}"
    paths = [f"{base}/input_files/.keep", f"{base}/product_files/.keep"]

    success = True
    for p in paths:
        try:
            await client.upload_file(settings.supabase_bucket_name, p, b"", "text/plain", overwrite=True)
            logger.info("📁 Carpeta creada: %s", p)
        except Exception as e:
            logger.error("Error creando carpeta %s: %s", p, e)
            success = False
    return success
# Fin del archivo backend\app\modules\files\services\storage\project_create_folder_storage.py






