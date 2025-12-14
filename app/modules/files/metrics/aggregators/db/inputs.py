
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/db/inputs.py

KPIs de archivos INSUMO (InputFile).

Calcula:
- overview: total de archivos y bytes totales
- by_status: conteo de archivos por estado de procesamiento
- daily_created: serie diaria de archivos creados

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import InputProcessingStatus


def inputs_overview(session: Session, project_id: Any) -> Dict[str, int]:
    """
    Devuelve un resumen general de archivos insumo para un proyecto::

        {
            "total_files": 10,
            "total_bytes": 123456
        }
    """
    if project_id is None:
        return {"total_files": 0, "total_bytes": 0}

    q_count = select(func.count()).where(InputFile.project_id == project_id)
    q_bytes = select(func.coalesce(func.sum(InputFile.input_file_size_bytes), 0)).where(
        InputFile.project_id == project_id
    )

    total_files = session.execute(q_count).scalar() or 0
    total_bytes = session.execute(q_bytes).scalar() or 0

    return {
        "total_files": int(total_files),
        "total_bytes": int(total_bytes),
    }


def inputs_by_status(session: Session, project_id: Any) -> List[Dict[str, Any]]:
    """
    Conteo de archivos insumo por estado de procesamiento.

    Retorna una lista de diccionarios::

        [
            {"status": "uploaded", "count": 5},
            {"status": "processed", "count": 3},
            ...
        ]
    """
    if project_id is None:
        return []

    q = (
        select(
            InputFile.input_file_status.label("status"),
            func.count().label("ct"),
        )
        .where(InputFile.project_id == project_id)
        .group_by("status")
    )
    rows = session.execute(q).all()

    out: List[Dict[str, Any]] = []
    for status, ct in rows:
        if isinstance(status, InputProcessingStatus):
            key = status.value
        else:
            key = str(status)
        out.append({"status": key, "count": int(ct or 0)})
    return out


def inputs_daily_created(
    session: Session,
    project_id: Any,
    days: int = 30,
) -> List[Tuple[str, int]]:
    """
    Serie diaria (fecha, conteo) de archivos insumo creados por día.

    Retorna una lista de tuplas (fecha_iso, conteo).
    """
    days = max(1, min(365, int(days or 0)))
    if project_id is None:
        return []

    q = (
        select(
            func.date_trunc("day", InputFile.input_file_uploaded_at).label("d"),
            func.count().label("ct"),
        )
        .where(InputFile.project_id == project_id)
        .group_by("d")
        .order_by("d".asc())
        .limit(365)
    )
    rows = session.execute(q).all()

    series: List[Tuple[str, int]] = []
    for d, ct in rows:
        if isinstance(d, datetime):
            key = d.date().isoformat()
        else:
            key = str(d)
        series.append((key, int(ct or 0)))
    return series[-days:]


__all__ = ["inputs_overview", "inputs_by_status", "inputs_daily_created"]

# Fin del archivo backend/app/modules/files/metrics/aggregators/db/inputs.py