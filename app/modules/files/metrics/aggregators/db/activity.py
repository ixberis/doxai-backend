
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/db/activity.py

Agregadores de actividad para archivos PRODUCTO.

Calcula:
- totales de eventos por tipo
- series diarias de descargas
- series diarias de generados

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.files.models.product_file_activity_models import ProductFileActivity
from app.modules.files.enums import ProductFileEvent


def _resolve_event_members(substring: str) -> List[ProductFileEvent]:
    """
    Devuelve los miembros de ProductFileEvent cuyo valor contiene
    el substring dado (en minúsculas).

    Esto permite ser robustos ante alias legacy en MAYÚSCULAS, ya
    que sólo nos interesa el value en minúsculas.

    Si no se encuentra ninguno, devuelve lista vacía.
    """
    members: List[ProductFileEvent] = []
    for ev in ProductFileEvent:  # type: ignore[operator]
        try:
            value = getattr(ev, "value", None)
            if isinstance(value, str) and substring in value.lower():
                members.append(ev)
        except Exception:
            continue
    return members


_DOWNLOAD_EVENTS: List[ProductFileEvent] = _resolve_event_members("download")
_GENERATED_EVENTS: List[ProductFileEvent] = _resolve_event_members("generated")


def activity_totals(session: Session, project_id: Any) -> Dict[str, int]:
    """
    Devuelve el número total de eventos de actividad por tipo para un proyecto.

    Retorna un diccionario del tipo::

        {
            "downloaded": 12,
            "generated": 4,
            "other": 3,
            ...
        }
    """
    if project_id is None:
        return {}

    stmt = (
        select(
            ProductFileActivity.event_type,
            func.count(ProductFileActivity.activity_id),
        )
        .where(ProductFileActivity.project_id == project_id)
        .group_by(ProductFileActivity.event_type)
    )

    rows = session.execute(stmt).all()
    out: Dict[str, int] = {}
    for ev, ct in rows:
        if isinstance(ev, ProductFileEvent):
            key = ev.value
        else:
            # Por si en la base quedó el valor como texto simple
            key = str(ev)
        out[key] = int(ct or 0)
    return out


def _daily_for_events(
    session: Session,
    project_id: Any,
    event_members: List[ProductFileEvent],
    days: int,
) -> List[Tuple[str, int]]:
    """
    Serie diaria (fecha, conteo) para un subconjunto de tipos de evento.

    Si la lista de miembros está vacía, devuelve lista vacía.
    """
    days = max(1, min(365, int(days or 0)))  # clamp
    if project_id is None or not event_members:
        return []

    stmt = (
        select(
            func.date_trunc("day", ProductFileActivity.event_at).label("d"),
            func.count(ProductFileActivity.activity_id).label("ct"),
        )
        .where(
            ProductFileActivity.project_id == project_id,
            ProductFileActivity.event_type.in_(event_members),
        )
        .group_by("d")
        .order_by("d".asc())
        .limit(365)
    )

    rows = session.execute(stmt).all()
    series: List[Tuple[str, int]] = []
    for d, ct in rows:
        # d puede venir como datetime; normalizamos a ISO date
        if isinstance(d, datetime):
            key = d.date().isoformat()
        else:
            key = str(d)
        series.append((key, int(ct or 0)))
    return series[-days:]


def downloads_daily(
    session: Session,
    project_id: Any,
    days: int = 30,
) -> List[Tuple[str, int]]:
    """
    Serie diaria de descargas de archivos producto.
    """
    return _daily_for_events(session, project_id, _DOWNLOAD_EVENTS, days)


def generated_daily(
    session: Session,
    project_id: Any,
    days: int = 30,
) -> List[Tuple[str, int]]:
    """
    Serie diaria de archivos producto generados.
    """
    return _daily_for_events(session, project_id, _GENERATED_EVENTS, days)


__all__ = ["activity_totals", "downloads_daily", "generated_daily"]

# Fin del archivo backend/app/modules/files/metrics/aggregators/db/activity.py
