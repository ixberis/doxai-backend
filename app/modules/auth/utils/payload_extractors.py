
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/payload_extractors.py

Helpers para transformar objetos de entrada (Pydantic, dict, etc.)
a diccionarios planos adecuados para uso en servicios.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


def as_dict(obj: Any) -> Dict[str, Any]:
    """
    Convierte un objeto de entrada en dict de forma tolerante:

    - Si es None → {}
    - Si es Mapping → dict(obj)
    - Si tiene .model_dump() (Pydantic v2) → model_dump()
    - Si tiene .dict() (Pydantic v1) → dict()
    - Si no, intenta dict(obj) como último recurso.
    """
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(obj, "dict"):
        return obj.dict()  # type: ignore[no-any-return]
    try:
        return dict(obj)  # type: ignore[arg-type]
    except Exception:
        return {"value": obj}


__all__ = ["as_dict"]

# Fin del script backend/app/modules/auth/utils/payload_extractors.py

