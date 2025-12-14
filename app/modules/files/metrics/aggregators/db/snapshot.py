
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/db/snapshot.py

Orquestador de snapshot: compone inputs/products/activity en un JSON estable.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .inputs import inputs_overview, inputs_by_status, inputs_daily_created
from .products import products_overview, products_by_type, products_daily_generated
from .activity import activity_totals, downloads_daily, generated_daily


class FilesMetricsAggregator:
    """
    Construye un snapshot compacto a partir de consultas DB.

    La forma del snapshot es::

        {
            "inputs": {
                "overview": {...},
                "status": [...],
                "daily_created": [...],
            },
            "products": {
                "overview": {...},
                "by_type": [...],
                "daily_generated": [...],
            },
            "activity": {
                "totals": {...},
                "downloads_daily": [...],
                "generated_daily": [...],
            },
        }
    """

    def build_snapshot(
        self,
        session: Session,
        *,
        project_id: Optional[Any],
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Construye un snapshot de métricas para el proyecto dado.

        Parámetros
        ----------
        session:
            Sesión síncrona de SQLAlchemy.
        project_id:
            Identificador del proyecto (UUID u otro tipo compatible con la
            columna project_id de las tablas de Files).
        days:
            Ventana de días a considerar para las series diarias (1-365).
        """
        days = max(1, min(365, int(days or 0)))

        if project_id is None:
            # Snapshot vacío pero con la misma estructura
            return {
                "inputs": {
                    "overview": {"total_files": 0, "total_bytes": 0},
                    "status": [],
                    "daily_created": [],
                },
                "products": {
                    "overview": {"total_files": 0, "total_bytes": 0},
                    "by_type": [],
                    "daily_generated": [],
                },
                "activity": {
                    "totals": {},
                    "downloads_daily": [],
                    "generated_daily": [],
                },
            }

        return {
            "inputs": {
                "overview": inputs_overview(session, project_id),
                "status": inputs_by_status(session, project_id),
                "daily_created": inputs_daily_created(
                    session,
                    project_id,
                    days=days,
                ),
            },
            "products": {
                "overview": products_overview(session, project_id),
                "by_type": products_by_type(session, project_id),
                "daily_generated": products_daily_generated(
                    session,
                    project_id,
                    days=days,
                ),
            },
            "activity": {
                "totals": activity_totals(session, project_id),
                "downloads_daily": downloads_daily(
                    session,
                    project_id,
                    days=days,
                ),
                "generated_daily": generated_daily(
                    session,
                    project_id,
                    days=days,
                ),
            },
        }


__all__ = ["FilesMetricsAggregator"]

# Fin del archivo backend/app/modules/files/metrics/aggregators/db/snapshot.py
