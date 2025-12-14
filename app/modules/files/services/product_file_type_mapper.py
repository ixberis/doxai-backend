# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/product_file_type_mapper.py

Utilidades para mapear tipos de contenido (MIME/extension) a ProductFileType.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.modules.files.enums import ProductFileType


EXTENSION_MAP = {
    # Documents
    "pdf": ProductFileType.report,
    "doc": ProductFileType.document,
    "docx": ProductFileType.document,
    "rtf": ProductFileType.document,
    "txt": ProductFileType.document,
    "md": ProductFileType.document,
    
    # Presentations
    "ppt": ProductFileType.presentation,
    "pptx": ProductFileType.presentation,
    
    # Spreadsheets
    "xls": ProductFileType.spreadsheet,
    "xlsx": ProductFileType.spreadsheet,
    "ods": ProductFileType.spreadsheet,
    
    # Datasets
    "csv": ProductFileType.dataset,
    "json": ProductFileType.dataset,
    "parquet": ProductFileType.dataset,
    "feather": ProductFileType.dataset,
    
    # Images
    "png": ProductFileType.image,
    "jpg": ProductFileType.image,
    "jpeg": ProductFileType.image,
    "gif": ProductFileType.image,
    "webp": ProductFileType.image,
    "tiff": ProductFileType.image,
    
    # Audio
    "mp3": ProductFileType.audio,
    "wav": ProductFileType.audio,
    "ogg": ProductFileType.audio,
    "m4a": ProductFileType.audio,
    
    # Video
    "mp4": ProductFileType.video,
    "mov": ProductFileType.video,
    "avi": ProductFileType.video,
    "mkv": ProductFileType.video,
    
    # Archives
    "zip": ProductFileType.archive,
}

MIME_MAP = {
    "application/pdf": ProductFileType.report,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ProductFileType.document,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ProductFileType.presentation,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ProductFileType.spreadsheet,
    "text/csv": ProductFileType.dataset,
    "application/json": ProductFileType.dataset,
    "image/png": ProductFileType.image,
    "image/jpeg": ProductFileType.image,
    "text/markdown": ProductFileType.document,
    "text/plain": ProductFileType.document,
    "application/zip": ProductFileType.archive,
}


def guess_from_extension(file_name: str) -> ProductFileType:
    """Mapea un nombre de archivo a ProductFileType usando su extensión."""
    if not file_name:
        return ProductFileType.other
    
    file_name_lower = file_name.lower()
    
    # Check for chart/graph keywords in name
    if any(keyword in file_name_lower for keyword in ["chart", "graph", "grafica", "plot"]):
        if file_name_lower.endswith(".png"):
            return ProductFileType.chart
    
    ext = Path(file_name).suffix.lstrip(".").lower()
    return EXTENSION_MAP.get(ext, ProductFileType.other)


def guess_from_mime(mime_type: str) -> ProductFileType:
    """Mapea un MIME type a ProductFileType."""
    if not mime_type:
        return ProductFileType.other
    
    mime_lower = mime_type.lower()
    
    # Direct match
    if mime_lower in MIME_MAP:
        return MIME_MAP[mime_lower]
    
    # Fallback patterns
    if mime_lower.startswith("application/pdf"):
        return ProductFileType.report
    if mime_lower.startswith("text/"):
        return ProductFileType.document
    if "spreadsheet" in mime_lower or "excel" in mime_lower:
        return ProductFileType.spreadsheet
    if mime_lower.startswith("image/"):
        return ProductFileType.image
    if mime_lower.startswith("audio/"):
        return ProductFileType.audio
    if mime_lower.startswith("video/"):
        return ProductFileType.video
    
    return ProductFileType.other


def guess_product_file_type(
    file_name: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> ProductFileType:
    """
    Mapea un archivo a ProductFileType usando MIME y/o extensión.
    Prioriza MIME sobre extensión cuando ambos están presentes.
    """
    # Priorizar MIME type si está presente y no es genérico
    if mime_type:
        mime_result = guess_from_mime(mime_type)
        if mime_result != ProductFileType.other:
            return mime_result
    
    # Fallback a extensión
    if file_name:
        ext_result = guess_from_extension(file_name)
        if ext_result != ProductFileType.other:
            return ext_result
    
    return ProductFileType.other


def guess_product_type(
    mime_type: Optional[str] = None,
    filename: Optional[str] = None,
    file_name: Optional[str] = None,
) -> ProductFileType:
    """
    Alias de compatibilidad para guess_product_file_type.
    
    Soporta tanto 'filename' como 'file_name' para compatibilidad
    con código legacy en facades.
    
    Args:
        mime_type: Tipo MIME del archivo
        filename: Nombre del archivo (alias legacy)
        file_name: Nombre del archivo (parámetro nuevo)
        
    Returns:
        ProductFileType inferido del MIME/nombre
    """
    # Usar file_name si se proporciona, sino filename
    name = file_name or filename
    return guess_product_file_type(file_name=name, mime_type=mime_type)


__all__ = [
    "guess_from_extension",
    "guess_from_mime",
    "guess_product_file_type",
    "guess_product_type",
]
