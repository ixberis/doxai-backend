
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/db/products.py

KPIs de archivos PRODUCTO:
- conteos por tipo/versión/backend
- bytes totales
- series diarias por generación

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.files.models.product_file_models import ProductFile
from .base import _bounds, _date_trunc, safe_execute


def products_overview(session: Session, project_id) -> Dict[str, Any]:
    total_q = select(func.count()).where(ProductFile.project_id == project_id)
    bytes_q = select(func.coalesce(func.sum(ProductFile.product_file_size_bytes), 0)).where(
        ProductFile.project_id == project_id
    )
    try:
        total = session.execute(total_q).scalar() or 0
        total_bytes = session.execute(bytes_q).scalar() or 0
    except Exception:
        total, total_bytes = 0, 0
    return {"count": int(total), "bytes": int(total_bytes)}


def products_by_type(session: Session, project_id) -> Dict[str, int]:
    q = (
        select(ProductFile.product_file_type, func.count().label("ct"))
        .where(ProductFile.project_id == project_id)
        .group_by(ProductFile.product_file_type)
    )
    rows = safe_execute(session, q)
    out: Dict[str, int] = {}
    for t, ct in rows:
        key = t.value if hasattr(t, "value") else (str(t) if t is not None else "unknown")
        out[key] = int(ct or 0)
    return out


def products_daily_generated(session: Session, project_id, days: int = 30) -> List[Tuple[str, int]]:
    q = (
        select(
            _date_trunc(ProductFile.product_file_generated_at).label("d"),
            func.count().label("ct"),
        )
        .where(ProductFile.project_id == project_id)
        .group_by("d")
        .order_by("d")
        .limit(365)
    )
    rows = safe_execute(session, q)
    return [(str(d), int(ct or 0)) for d, ct in rows][-days:]


# Fin del archivo backend/app/modules/files/metrics/aggregators/db/products.py
