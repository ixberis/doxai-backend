# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/enums/ocr_optimization_enum.py

Estrategia de OCR: prioriza latencia (fast), precisión (accurate) o equilibrio (balanced).
Se usa al convertir documentos escaneados/imagen→texto (Azure Cognitive Services OCR).

Uso recomendado: utilizar 'balanced' como default para comportamiento consistente
entre servicios, ajustando a 'fast' o 'accurate' según necesidades específicas.

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class OcrOptimization(StrEnum):
    """Estrategia de optimización para OCR."""
    fast     = "fast"      # menor latencia/costo
    accurate = "accurate"  # mejor calidad/recall
    balanced = "balanced"  # trade-off intermedio


def as_pg_enum(name: str = "ocr_optimization_enum", schema: str | None = None):
    # Usar valores posicionales (mínúsculas) y exponer enum_class
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    pg = PG_ENUM(
        *[e.value for e in OcrOptimization],
        name=name,
        schema=schema,
        create_type=False,
    )
    pg.enum_class = OcrOptimization
    return pg


__all__ = ["OcrOptimization", "as_pg_enum"]

