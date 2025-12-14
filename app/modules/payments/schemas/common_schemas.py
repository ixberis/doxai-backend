
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/common_schemas.py

Esquemas comunes (por ahora, sólo metadatos de paginación) para el módulo Payments.

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageMeta(BaseModel):
    """
    Metadatos de paginación para respuestas con listas.
    """

    total: int = Field(ge=0, description="Número total de registros.")
    limit: int = Field(ge=1, description="Límite de registros por página.")
    offset: int = Field(ge=0, description="Offset actual de la consulta.")
    page: int = Field(ge=1, description="Página actual (1-based).")
    pages: int = Field(ge=0, description="Número total de páginas.")


__all__ = ["PageMeta"]

# Fin del archivo backend/app/modules/payments/schemas/common_schemas.py
