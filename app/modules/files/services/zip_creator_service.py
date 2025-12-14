# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/zip_creator_service.py

Servicio para creación de archivos ZIP.
"""

from __future__ import annotations

import io
import zipfile
from typing import Dict


def create_zip_from_bytes(files: Dict[str, bytes]) -> bytes:
    """
    Crea un archivo ZIP en memoria a partir de un diccionario de archivos.
    
    Args:
        files: Diccionario de nombre -> contenido (bytes)
        
    Returns:
        Bytes del archivo ZIP
    """
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    
    return buffer.getvalue()


class ZipCreatorService:
    """Servicio para creación de archivos ZIP."""

    def __init__(self, tmp_dir=None):
        self.tmp_dir = tmp_dir

    def create_zip(
        self,
        files: Dict[str, bytes],
        chunk_size: int = 32768,
    ) -> bytes:
        """
        Crea un ZIP en memoria a partir de archivos.
        
        Args:
            files: Diccionario de nombre -> contenido
            chunk_size: Tamaño de chunks para escritura
            
        Returns:
            Bytes del archivo ZIP
            
        Raises:
            ValueError: Si el input no es dict[str, bytes]
        """
        if not isinstance(files, dict):
            raise ValueError("files must be a dict[str, bytes]")

        # Usar el servicio existente
        return create_zip_from_bytes(files)


class BrokenZipCreator(ZipCreatorService):
    """Versión de prueba que simula fallos en ciertos archivos."""

    def create_zip(self, files: Dict[str, bytes], chunk_size: int = 32768) -> bytes:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                if "fail" in name.lower():
                    # Skip archivos que contienen 'fail' en el nombre
                    continue
                zf.writestr(name, content)

        return buffer.getvalue()


__all__ = ["ZipCreatorService", "BrokenZipCreator"]
