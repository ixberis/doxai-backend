
# -*- coding: utf-8 -*-
"""
backend\app\routes\master_routes.py

Router maestro con dos capas:
  - /api/... (interno/estable)
  - rutas públicas sin prefijo

Ajustes:
- Mantiene la lógica de montado de Auth/Admin/Payments/Projects/Files/RAG.
- Importa y monta los routers internos de métricas de Auth y Files en la capa
  pública e interna, para facilitar scraping interno/ingress.
- Integra el módulo Projects (incluye sus métricas bajo /projects/metrics/*)
  en ambas capas (api y pública), espejo de Auth.
- Integra el router principal de Files (/files/*) y el router de métricas de Files
  (endpoints /files/metrics/*) en ambas capas.

Autor: Ixchel Beristain
Fecha: 2025-11-11
"""
from __future__ import annotations

import logging
import os
from importlib import import_module
from typing import Iterable, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Capas principales
api = APIRouter(prefix="/api")
public = APIRouter(prefix="")  # sin prefijo

_loaded: list[str] = []  # trazabilidad/debug


def _include(target: APIRouter, router: APIRouter, name: str) -> None:
    """Incluye un router en la capa dada y registra trazabilidad en logs."""
    target.include_router(router)
    _loaded.append(f"{target.prefix or '/'}:{name}")
    logger.info(
        "✅ Router '%s' montado en prefix '%s' (router.prefix='%s')",
        name,
        target.prefix or "/",
        getattr(router, "prefix", ""),
    )


def _try_import_router(
    module_candidates: Iterable[str],
    attr: str = "router",
) -> Optional[APIRouter]:
    """
    Intenta importar un APIRouter desde una lista de módulos candidatos.

    Args:
        module_candidates: Lista de rutas de módulo a probar.
        attr: Nombre del atributo dentro del módulo (por defecto 'router').

    Returns:
        El APIRouter encontrado o None si ninguno aplica.
    """
    for mod_path in module_candidates:
        try:
            mod = import_module(mod_path)
            r = getattr(mod, attr, None)
            if r:
                logger.debug(
                    "✔ Cargado router desde %s.%s (router.prefix='%s')",
                    mod_path,
                    attr,
                    getattr(r, "prefix", ""),
                )
                return r
        except Exception as e:
            logger.debug("… No se pudo cargar %s: %s", mod_path, e)
    return None


# ─────────────────────────────────────────
# AUTH (get_auth_routers → público + /api)
# ─────────────────────────────────────────
try:
    from app.modules.auth.routes import get_auth_routers  # type: ignore

    for r in get_auth_routers():
        _include(api, r, f"auth.{r.tags[0] if r.tags else 'unknown'}")
        _include(public, r, f"auth.{r.tags[0] if r.tags else 'unknown'}")
except Exception as e:  # pragma: no cover
    logger.warning("Auth routers no montados: %s", e)


# ─────────────────────────────────────────
# ADMIN (endpoints administrativos)
# ─────────────────────────────────────────
try:
    from app.modules.admin.routes import get_admin_routers  # type: ignore

    for r in get_admin_routers():
        # Solo montar en /api (no en público por seguridad)
        _include(api, r, f"admin.{r.tags[0] if r.tags else 'unknown'}")
except Exception as e:  # pragma: no cover
    logger.warning("Admin routers no montados: %s", e)


# ─────────────────────────────────────────
# PAYMENTS: STUBS vs Routers Reales
# ─────────────────────────────────────────
USE_STUBS = os.getenv("USE_PAYMENT_STUBS", "").lower() == "true"
API_PREFIX = "/api/payments"  # reservado/por si se requiere en el futuro

if USE_STUBS:
    # 1) Cargar stubs desde cualquiera de los nombres posibles
    stubs = _try_import_router(
        [
            "app.modules.payments.routes._stubs_tests_routes",  # nombre final
            "app.modules.payments.routes._stubs_test_routes",  # alterno previo
        ]
    )
    if stubs:
        # Montar stubs SOLO en public para evitar conflictos
        # El router tiene prefix="/payments"
        _include(public, stubs, "payments.stubs(/payments)")
    # IMPORTANTE: no montar routers reales cuando se usan stubs
else:
    # Routers reales de Payments + alias general /payments
    payments_main = _try_import_router(
        [
            "app.modules.payments.routes",
        ]
    )
    if payments_main:
        _include(public, payments_main, "payments.main")
        logger.info("✅ Módulo payments montado exitosamente desde routes/__init__.py")
    else:
        logger.warning("⚠ No se pudo montar el módulo payments desde routes/__init__.py")


# ─────────────────────────────────────────
# PROJECTS (router principal incluye métricas)
# ─────────────────────────────────────────
try:
    # El ensamblador de Projects ya incluye:
    # - CRUD, Lifecycle, Files, Queries
    # - Metrics (Prometheus y snapshots) bajo /projects/metrics/*
    from app.modules.projects.routes import get_projects_router  # type: ignore

    # Crear instancias separadas para cada capa (evita reuso del mismo objeto)
    projects_router_api = get_projects_router()
    projects_router_public = get_projects_router()

    _include(api, projects_router_api, "projects.main")
    _include(public, projects_router_public, "projects.main")
except Exception as e:  # pragma: no cover
    logger.warning("Projects routers no montados: %s", e)


# ─────────────────────────────────────────
# FILES — Router principal (/files/*)
# ─────────────────────────────────────────
try:
    files_main_router = _try_import_router(
        [
            # preferido: router explícito del módulo Files
            "app.modules.files.routes.files_routes",
            # alterno: si __init__.py de routes re-exporta `router`
            "app.modules.files.routes",
        ]
    )
    if files_main_router:
        _include(api, files_main_router, "files.main")
        _include(public, files_main_router, "files.main")
    else:
        logger.info("(Opcional) Router principal de Files no encontrado")
except Exception as e:  # pragma: no cover
    logger.info("(Opcional) Router principal de Files no montado: %s", e)


# ─────────────────────────────────────────
# FILES — Métricas (/files/metrics/*)
# ─────────────────────────────────────────
try:
    files_metrics_router = _try_import_router(
        [
            # nuevo ensamblador (recomendado)
            "app.modules.files.metrics.routes",
            # alterno por compatibilidad si existe un archivo único
            "app.modules.files.metrics.routes.files_metrics_routes",
        ]
    )
    if files_metrics_router:
        # Montamos en ambas capas para simetría con Projects/Auth
        _include(api, files_metrics_router, "files.metrics")
        _include(public, files_metrics_router, "files.metrics")
    else:
        logger.info("(Opcional) Router de métricas de Files no encontrado")
except Exception as e:  # pragma: no cover
    logger.info("(Opcional) Router de métricas de Files no montado: %s", e)


# ─────────────────────────────────────────
# RAG — Router principal (/rag/*)
# ─────────────────────────────────────────
try:
    from app.modules.rag.routes import router as rag_main_router

    # Solo incluir en public por ahora para evitar conflictos
    _include(public, rag_main_router, "rag.main")
    logger.info("✅ Módulo RAG montado exitosamente")
except Exception as e:  # pragma: no cover
    logger.error("❌ Router de RAG no montado: %s", e, exc_info=True)


# ─────────────────────────────────────────
# BILLING — Router de paquetes de créditos
# ─────────────────────────────────────────
try:
    from app.modules.billing import router as billing_router

    # Montar en /api/billing (solo capa api)
    _include(api, billing_router, "billing.main")
    logger.info("✅ Módulo Billing montado exitosamente")
except Exception as e:  # pragma: no cover
    logger.warning("⚠ Router de Billing no montado: %s", e)


# ─────────────────────────────────────────
# INTERNAL — Email test endpoint (solo dev)
# ─────────────────────────────────────────
try:
    from app.routes.internal_email_routes import router as internal_email_router
    
    # Solo montar en api (rutas internas)
    _include(api, internal_email_router, "internal.email")
    logger.info("✅ Endpoint interno de email montado")
except Exception as e:  # pragma: no cover
    logger.debug("Endpoint interno de email no montado: %s", e)


@api.get("/_debug/loaded-routers")
def loaded_routers():
    """Endpoint de debug para ver qué routers se montaron y en qué capa."""
    return {"loaded": _loaded}


router = APIRouter()
router.include_router(api)
router.include_router(public)

# Fin del script bbackend\app\routes\master_routes.py
