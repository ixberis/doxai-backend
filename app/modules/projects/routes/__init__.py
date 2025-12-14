
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/__init__.py

Router principal del módulo Projects.
Compone subrouters de:
- projects_crud (CRUD)
- projects_lifecycle (status/state/archive)
- files (operaciones de archivos)
- queries (consultas/auditoría)
- metrics (Prometheus y snapshots)

Ajuste 10/11/2025:
- Refactor menor de ensamblado: orden y coherencia con FastAPI v2.
- Define response_model_exclude_none=True por defecto.
- Verifica presencia de router de métricas antes de incluirlo.
- Mejora legibilidad y consistencia de imports.

Autor: Ixchel Beristain
Fecha de actualización: 10/11/2025
"""
from fastapi import APIRouter

# Subrouters principales
from .projects_crud import router as projects_crud_router
from .projects_lifecycle import router as projects_lifecycle_router
from .files import router as files_router
from .queries import router as queries_router

# Subrouter de métricas (ensamblador dedicado)
from app.modules.projects.metrics.routes import get_projects_metrics_router


def get_projects_router() -> APIRouter:
    """
    Devuelve el router principal del módulo de proyectos.
    Ensambla los subrouters con el prefijo /projects.

    Orden de ensamblado:
      1. Consultas y auditoría (incluye /ready)
      2. CRUD principal (/{project_id})
      3. Ciclo de vida (state/status/archive)
      4. Archivos asociados al proyecto (/files/*)
      5. Métricas y Prometheus (/projects/metrics/*)

    Nota:
      Se activa `response_model_exclude_none=True` globalmente
      para reducir payloads en respuestas de lectura.
    """
    router = APIRouter(
        prefix="/projects",
        tags=["projects"],
        responses={404: {"description": "No encontrado"}},
    )

    # Configuración global de serialización (FastAPI v2)
    router.default_response_model_exclude_none = True

    # 1. Consultas y auditoría (incluye /ready)
    router.include_router(queries_router)

    # 2. CRUD de proyectos
    router.include_router(projects_crud_router)

    # 3. Ciclo de vida: status/state/archive
    router.include_router(projects_lifecycle_router)

    # 4. Archivos asociados al proyecto
    router.include_router(files_router)

    # 5. Métricas (Prometheus y snapshots)
    try:
        metrics_router = get_projects_metrics_router()
        if metrics_router:
            router.include_router(metrics_router)
    except Exception as e:
        # fallback seguro en caso de error de import
        print(f"[WARN] No se pudo cargar router de métricas de Projects: {e}")

    return router


# Fin del archivo backend/app/modules/projects/routes/__init__.py


