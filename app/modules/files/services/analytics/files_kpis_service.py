
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/analytics/files_kpis_service.py

Servicio de lectura de KPIs del módulo Files desde vistas/funciones SQL:
- kpi_files_pipeline
- kpi_files_volume
- kpi_files_downloads_30d
- fn_refresh_files_materialized_views()

Compatibilidad con Session y AsyncSession.
Devuelve estructuras listas para serializar a JSON.

Autor: DoxAI
Fecha: 2025-11-10
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession


class FilesKpisService:
    """Lectura de KPIs desde vistas/materializadas del módulo Files."""

    def __init__(self, db: Session | AsyncSession):
        self.db = db

    async def _exec(self, stmt):
        result = self.db.execute(stmt)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    # ---------------------- KPIs: lecturas ----------------------

    async def get_pipeline_status(self, project_id) -> List[Dict[str, Any]]:
        """
        SELECT * FROM kpi_files_pipeline WHERE project_id = :pid
        Regresa filas con el estado del pipeline de insumos.
        """
        stmt = text(
            "SELECT * FROM kpi_files_pipeline WHERE project_id = :pid ORDER BY status"
        ).bindparams(pid=project_id)
        res = await self._exec(stmt)
        return [dict(r._mapping) for r in res]  # list[dict]

    async def get_volume_by_day(self, project_id) -> List[Dict[str, Any]]:
        """
        SELECT * FROM kpi_files_volume WHERE project_id = :pid
        Regresa series diarias por tipo/categoría (según la vista).
        """
        stmt = text(
            "SELECT * FROM kpi_files_volume WHERE project_id = :pid ORDER BY day ASC"
        ).bindparams(pid=project_id)
        res = await self._exec(stmt)
        return [dict(r._mapping) for r in res]

    async def get_downloads_30d(self, project_id) -> List[Dict[str, Any]]:
        """
        SELECT * FROM kpi_files_downloads_30d WHERE project_id = :pid
        Regresa descargas por día en los últimos 30 días.
        """
        stmt = text(
            "SELECT * FROM kpi_files_downloads_30d WHERE project_id = :pid ORDER BY day ASC"
        ).bindparams(pid=project_id)
        res = await self._exec(stmt)
        return [dict(r._mapping) for r in res]

    # ---------------------- KPIs: operación ----------------------

    async def refresh_materialized(self) -> Dict[str, Any]:
        """
        Ejecuta la función de refresco de materializadas del módulo Files.
        Requiere credenciales de service_role (validación en la capa de rutas).
        """
        stmt = text("SELECT fn_refresh_files_materialized_views() AS ok;")
        res = await self._exec(stmt)
        row = res.first()
        return {"ok": bool(row and list(row)[0])}


# Fin del archivo backend/app/modules/files/services/analytics/files_kpis_service.py
