
# -*- coding: utf-8 -*-
"""
backend/app/utils/hashing.py

Utilidades de hash deterministas para deduplicación de embeddings
y generación de IDs estables de chunks.

Autor: Sistema DoxAI
Fecha: 05/09/2025
"""

from __future__ import annotations

import hashlib
from typing import Optional, Union, Any
from uuid import UUID

# Normalizador de texto (usa el oficial si existe; fallback simple si no)
try:
    from app.shared.utils.text_normalizer import normalize_for_hash as _external_normalize_text  # type: ignore
except Exception:  # pragma: no cover
    _external_normalize_text = None

def _normalize_text_fallback(text: str) -> str:
    return " ".join((text or "").split())

def _normalize(text: str) -> str:
    """Usa el normalizador oficial si existe; si no, fallback local (no exportado)."""
    if _external_normalize_text is not None:
        try:
            return _external_normalize_text(text)  # type: ignore[misc]
        except Exception:
            # si el normalizador externo falla, usamos fallback para robustez
            pass
    return _normalize_text_fallback(text)


# ========================
# Hash helpers (utilidades)
# ========================

def sha1_hex(data: Union[str, bytes]) -> str:
    """
    Genera hash SHA1 determinista en formato hexadecimal.

    Args:
        data: Texto o bytes a hashear

    Returns:
        Hash SHA1 en formato hex (40 caracteres)
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def blake2b_hex(data: Union[str, bytes], digest_size: int = 32) -> str:
    """
    Genera hash BLAKE2b más rápido que SHA1 para grandes volúmenes.

    Args:
        data: Texto o bytes a hashear
        digest_size: Tamaño del digest (16-64 bytes)

    Returns:
        Hash BLAKE2b en formato hex
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.blake2b(data, digest_size=digest_size).hexdigest()


# =============================================
# ID estable para chunks (implementación canónica)
# =============================================

def _to_str_uuid(val: Union[str, UUID]) -> str:
    return str(val).strip().lower()


def stable_chunk_id(
    project_id: Union[str, UUID],
    file_storage_path: str,
    page: Optional[int],
    local_index: Optional[int],
    text_or_preview: Optional[str] = None,
    *,
    text: Optional[str] = None,
    text_preview: Optional[str] = None,
) -> str:
    """
    Genera un ID estable para un chunk combinando metadatos + texto normalizado.

    Compatibilidad retro:
    - Históricamente, el 5º parámetro posicional fue `text_preview`.
      Este se sigue aceptando como `text_or_preview`.
    - Nueva API: usar argumentos con nombre `text=` (preferible, texto completo)
      o `text_preview=` si sólo se dispone de una vista previa.

    Args:
        project_id: UUID del proyecto (UUID o str)
        file_storage_path: Ruta del archivo en storage (se normaliza a lower)
        page: Número de página (None → -1)
        local_index: Índice local del chunk (None → -1)
        text_or_preview: (retrocompatibilidad) texto o preview pasado como 5º arg posicional
        text: Texto completo del chunk (preferido si está disponible)
        text_preview: Vista previa del texto si no se tiene el texto completo

    Returns:
        str: Hash SHA1 hex (40 chars) estable que identifica el chunk
    """
    pid = _to_str_uuid(project_id)
    fpath = (file_storage_path or "").strip().lower()
    p = -1 if page is None else int(page)
    idx = -1 if local_index is None else int(local_index)

    # Resolución de fuente de texto con prioridad:
    # 1) text (nuevo y preferido)
    # 2) text_or_preview (quinto posicional histórico)
    # 3) text_preview (keyword legacy)
    source: Optional[str] = text if text is not None else text_or_preview
    if source is None:
        source = text_preview

    # Normaliza y recorta para evitar payloads gigantes (mantener estabilidad)
    base = _normalize(source or "")[:240]

    payload = f"{pid}|{fpath}|{p}|{idx}|{base}"
    return sha1_hex(payload)

__all__ = ["sha1_hex", "blake2b_hex", "stable_chunk_id"]

# Fin del archivo






