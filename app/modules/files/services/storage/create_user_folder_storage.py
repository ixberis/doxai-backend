
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/create_user_folder_storage.py

Este módulo crea una carpeta personal para un usuario dentro del bucket de Supabase Storage.
Debido a que Supabase Storage no permite crear carpetas vacías, se simula la creación
subiendo un archivo marcador `.keep` dentro de la ruta correspondiente al `user_id`.

Autor: Ixchel Beristain
Actualizado: 02/11/2025
"""

from __future__ import annotations

import logging
from app.shared.utils.http_storage_client import get_http_storage_client
from app.shared.config import settings

logger = logging.getLogger(__name__)


async def create_user_storage_folder(user_id: str) -> None:
    """
    Simula la creación de una carpeta en Supabase Storage subiendo un archivo vacío
    llamado `.keep` en la ruta del usuario.

    Args:
        user_id (str): Identificador único del usuario (UUID en string).

    Notas:
        - No interrumpe el flujo de activación si falla el upload; solo deja log.
    """
    if not user_id:
        logger.warning("create_user_storage_folder: user_id vacío")
        return

    placeholder_path = f"{user_id}/.keep"
    upload_url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_bucket_name}/{placeholder_path}"

    try:
        client = get_http_storage_client()
        # Usamos la API del cliente HTTP (envía `x-upsert` si fuese necesario)
        await client.upload_file(
            bucket=settings.supabase_bucket_name,
            path=placeholder_path,
            file_data=b"",
            content_type="text/plain",
            overwrite=True,
        )
        logger.info("📁 Carpeta simulada creada en Supabase para el usuario %s (%s)", user_id, upload_url)
    except Exception as e:
        logger.warning("No se pudo crear la carpeta del usuario %s: %s", user_id, str(e))
        # No levantar excepción: la activación del usuario no debe fallar por esto.
# Fin del archivo backend\app\modules\files\services\storage\create_user_folder_storage.py