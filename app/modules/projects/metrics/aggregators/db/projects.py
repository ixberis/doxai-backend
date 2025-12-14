
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/aggregators/db/projects.py

Agregadores de métricas desde BD para el módulo Projects (nivel proyecto).
Paridad conceptual con Payments: se obtienen conteos por estado/status,
total de proyectos, ventanas temporales básicas y lead time created→ready.

Ajuste 08/11/2025:
- Implementa funciones ORM genéricas (compatibles con SQLite/Postgres).
- Evita dependencias de extensiones específicas (percentiles quedan opcionales).

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select, literal_column, cast, String, literal
from sqlalchemy.orm import Session

# Modelos y enums del módulo Projects
from app.modules.projects.models.project_models import Project  # type: ignore
from app.modules.projects.enums.project_state_enum import ProjectState  # type: ignore
from app.modules.projects.enums.project_status_enum import ProjectStatus  # type: ignore

# Schemas de métricas para snapshot
from app.modules.projects.metrics.schemas.metrics_schemas import (
    TimeBucketValue,
    ProjectsByState,
    ProjectsByStatus,
    ProjectReadyLeadTime,
)


class ProjectsDBAggregator:
    """
    Agregador de métricas desde BD para Projects.
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------------
    # Totales y distribuciones
    # ---------------------------------------------------------------------
    def projects_total(self) -> int:
        """
        Total de proyectos (no filtramos por owner aquí; se asume scope global/tenant).
        """
        stmt = select(func.count(literal_column("*"))).select_from(Project)
        return int(self.db.execute(stmt).scalar() or 0)

    def projects_by_state(self) -> ProjectsByState:
        """
        Conteo por estado técnico (workflow).
        """
        stmt = (
            select(cast(Project.state, String), func.count(literal_column("*")))
            .group_by(Project.state)
        )
        rows = self.db.execute(stmt).all()
        items: Dict[str, int] = {str(k or ""): int(v or 0) for k, v in rows}
        total = sum(items.values())
        return ProjectsByState(items=items, total=total)

    def projects_by_status(self) -> ProjectsByStatus:
        """
        Conteo por status administrativo.
        """
        stmt = (
            select(cast(Project.status, String), func.count(literal_column("*")))
            .group_by(Project.status)
        )
        rows = self.db.execute(stmt).all()
        items: Dict[str, int] = {str(k or ""): int(v or 0) for k, v in rows}
        total = sum(items.values())
        return ProjectsByStatus(items=items, total=total)

    # ---------------------------------------------------------------------
    # Series / ventanas temporales
    # ---------------------------------------------------------------------
    def projects_ready_by_window(self, date_trunc: str = "day", limit_buckets: int = 30) -> List[TimeBucketValue]:
        """
        Conteo de proyectos en estado READY agrupados por ventana temporal.
        - Para Postgres se intenta usar date_trunc; para SQLite se usa DATE(ready_at).

        Args:
            date_trunc: "day" | "week" | "month" (sugerido "day")
            limit_buckets: máximo de buckets a devolver (ordenado desc por fecha)
        """
        # Detectar si existe date_trunc (Postgres) vs fallback (SQLite)
        # Nota: usamos un try simple; si falla el compilador/dialecto, caemos al fallback.
        bucket_label = "bucket_start"

        try:
            # Postgres-like
            bucket_expr = func.date_trunc(date_trunc, Project.ready_at)
            stmt = (
                select(bucket_expr.label(bucket_label), func.count(literal_column("*")))
                .where(Project.state == cast(literal("ready"), Project.state.type))
                .group_by(bucket_expr)
                .order_by(bucket_expr.desc())
                .limit(limit_buckets)
            )
            rows = self.db.execute(stmt).all()
            buckets = [
                TimeBucketValue(bucket_start=(r[0].isoformat() if isinstance(r[0], datetime) else str(r[0])), value=float(r[1] or 0.0))
                for r in rows
            ]
            return list(reversed(buckets))  # ascendente
        except Exception:
            # Fallback genérico (SQLite): DATE(ready_at)
            bucket_expr = func.date(Project.ready_at)
            stmt = (
                select(bucket_expr.label(bucket_label), func.count(literal_column("*")))
                .where(Project.state == cast(literal("ready"), Project.state.type))
                .group_by(bucket_expr)
                .order_by(bucket_expr.desc())
                .limit(limit_buckets)
            )
            rows = self.db.execute(stmt).all()
            buckets = [
                TimeBucketValue(bucket_start=str(r[0]), value=float(r[1] or 0.0))
                for r in rows
            ]
            return list(reversed(buckets))  # ascendente

    # ---------------------------------------------------------------------
    # Lead time created -> ready
    # ---------------------------------------------------------------------
    def ready_lead_time(self) -> ProjectReadyLeadTime:
        """
        Calcula promedios simples del tiempo (en segundos) desde created_at -> ready_at
        para proyectos que ya están en READY. Se deja solo el promedio por compatibilidad
        multi-dialecto; percentiles pueden quedar en None si no hay soporte nativo.
        """
        # AVG( EXTRACT(EPOCH FROM (ready_at - created_at)) )
        # Fallback multi-dialecto: usar julianday en SQLite no es portable vía ORM sin raw SQL.
        # Aquí intentamos la resta de timestamps y confiamos en el backend.
        try:
            delta_seconds_avg = select(
                func.avg(func.extract("epoch", Project.ready_at - Project.created_at))
            ).where(
                Project.ready_at.isnot(None)
            )
            avg_val = self.db.execute(delta_seconds_avg).scalar()
            avg_seconds = float(avg_val) if avg_val is not None else None
            return ProjectReadyLeadTime(
                avg_seconds=avg_seconds,
                p50_seconds=None,
                p90_seconds=None,
                p99_seconds=None,
            )
        except Exception:
            # Fallback básico (None) si el dialecto no soporta extract epoch
            return ProjectReadyLeadTime(
                avg_seconds=None,
                p50_seconds=None,
                p90_seconds=None,
                p99_seconds=None,
            )

# Fin del archivo backend\app\modules\projects\metrics\aggregators\db\projects.py