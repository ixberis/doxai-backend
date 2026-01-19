# -*- coding: utf-8 -*-
"""
backend/app/routes/master_routes.py

Router maestro con arquitectura de capas claramente definida.

═══════════════════════════════════════════════════════════════════════════════
ARQUITECTURA DE CAPAS
═══════════════════════════════════════════════════════════════════════════════
- `/api/...` → rutas API estables (uso interno/externo)
- `/` → rutas públicas sin prefijo
- `/_internal/...` → rutas internas (solo en capa API)

═══════════════════════════════════════════════════════════════════════════════
PROBLEMA ANTERIOR (pre 2025-12-15)
═══════════════════════════════════════════════════════════════════════════════
Los routers se montaban múltiples veces (3-5 veces cada uno) debido a:

1. DOBLE MONTAJE AUTOMÁTICO: El loop `for r in get_auth_routers()` llamaba a
   `_include(api, r, ...)` Y `_include(public, r, ...)` para el MISMO objeto
   router, sin verificar si ya estaba montado.

2. MONTAJE PARALELO EN app.py: La función `_include_module_routers()` en
   `app/shared/core/app.py` escaneaba dinámicamente todos los módulos y
   montaba cualquier `router` encontrado, EN PARALELO al montaje explícito
   de master_routes.py.

3. ROUTERS SIN TAGS: Algunos routers (ej: metrics_auth_router) no tenían
   `tags=[]` definido, apareciendo en logs como "auth.unknown".

Resultado: logs mostraban "Router 'auth.Authentication' montado en '/' " 
repetido 3-5 veces, generando ruido y riesgo de shadowing.

═══════════════════════════════════════════════════════════════════════════════
SOLUCIÓN ACTUAL (determinista)
═══════════════════════════════════════════════════════════════════════════════
1. DEDUPLICACIÓN POR id(router): Sets `_mounted_api` y `_mounted_public`
   rastrean qué routers ya fueron montados, evitando duplicados.

2. FUNCIÓN `_include_once()`: Verifica antes de montar, loguea skip si
   ya existe, garantiza un solo montaje por capa.

3. LIMPIEZA PREVENTIVA de app.py: Se eliminó `_include_module_routers()`
   para que NO haya montaje automático paralelo. Esta limpieza es PREVENTIVA
   porque main.py no usaba create_app(), pero evita confusión futura.

4. TAGS EXPLÍCITOS: Todos los routers ahora tienen tags definidos.

Resultado: cada router aparece EXACTAMENTE una vez por capa en logs.

═══════════════════════════════════════════════════════════════════════════════
PRINCIPIOS DE DISEÑO
═══════════════════════════════════════════════════════════════════════════════
1. Cada router se monta UNA SOLA VEZ por capa (sin duplicados)
2. La decisión de capa es explícita (api_only, public_only, both)
3. Los routers internos (/_internal/*) solo van en la capa API
4. Logging determinista para diagnóstico

Autor: Ixchel Beristain
Fecha: 2025-12-15
"""
from __future__ import annotations

import logging
import os
from importlib import import_module
from typing import Optional, Set

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Capas principales
api = APIRouter(prefix="/api")
public = APIRouter(prefix="")  # sin prefijo

# Registro de routers ya montados (por id) para evitar duplicados
_mounted_api: Set[int] = set()
_mounted_public: Set[int] = set()
_loaded: list[str] = []  # trazabilidad/debug


def _get_router_name(router: APIRouter) -> str:
    """Obtiene un nombre descriptivo para el router."""
    if router.tags:
        return router.tags[0]
    if router.prefix:
        return router.prefix.strip("/").replace("/", ".") or "root"
    return "unnamed"


def _include_once(
    target: APIRouter,
    router: APIRouter,
    module_name: str,
    mounted_set: Set[int],
) -> bool:
    """
    Incluye un router en la capa dada SOLO si no está ya montado.
    
    Returns:
        True si se montó, False si ya estaba montado.
    """
    router_id = id(router)
    if router_id in mounted_set:
        logger.debug(
            "⏭ Router '%s.%s' ya montado en '%s', saltando",
            module_name,
            _get_router_name(router),
            target.prefix or "/",
        )
        return False
    
    target.include_router(router)
    mounted_set.add(router_id)
    
    router_name = f"{module_name}.{_get_router_name(router)}"
    _loaded.append(f"{target.prefix or '/'}:{router_name}")
    logger.info(
        "✅ Router '%s' montado en '%s' (prefix='%s')",
        router_name,
        target.prefix or "/",
        router.prefix or "",
    )
    return True


def _try_import_router(
    module_candidates: list[str],
    attr: str = "router",
) -> Optional[APIRouter]:
    """
    Intenta importar un APIRouter desde una lista de módulos candidatos.
    """
    for mod_path in module_candidates:
        try:
            mod = import_module(mod_path)
            r = getattr(mod, attr, None)
            if r:
                logger.debug(
                    "✔ Cargado router desde %s.%s (prefix='%s')",
                    mod_path,
                    attr,
                    getattr(r, "prefix", ""),
                )
                return r
        except Exception as e:
            logger.debug("… No se pudo cargar %s: %s", mod_path, e)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# AUTH (CRITICAL - FAIL FAST IN PRODUCTION)
# ═══════════════════════════════════════════════════════════════════════════
# Auth routers se montan en AMBAS capas (api y public) para compatibilidad
# EXCEPCIÓN: rutas /_internal/* van SOLO en public (sin prefix /api)
# para que sean accesibles en /_internal/... directamente.
#
# FAIL-FAST POLICY:
# - En producción (ENVIRONMENT=production): raise RuntimeError, app NO arranca
# - En desarrollo/tests: log warning explícito, continuar sin auth
_is_production = os.environ.get("ENVIRONMENT", "").lower() == "production"

try:
    from app.modules.auth.routes import get_auth_routers

    _auth_routers = list(get_auth_routers())
    if not _auth_routers:
        raise RuntimeError("get_auth_routers() retornó lista vacía - auth no disponible")
    
    for r in _auth_routers:
        name = _get_router_name(r)
        # Routers internos (/_internal/*) solo en PUBLIC (sin /api prefix)
        # Esto permite acceso directo a /_internal/auth/metrics/snapshot
        if r.prefix and r.prefix.startswith("/_internal"):
            _include_once(public, r, "auth", _mounted_public)
        else:
            # Routers públicos en ambas capas
            _include_once(api, r, "auth", _mounted_api)
            _include_once(public, r, "auth", _mounted_public)
    
    logger.info("✅ Auth routers montados correctamente (%d routers)", len(_auth_routers))

except Exception as e:
    if _is_production:
        # PRODUCTION: Fail-fast - la app NO debe arrancar sin auth
        logger.critical(
            "❌ CRITICAL: Auth routers FAILED to mount in PRODUCTION - aborting startup",
            exc_info=True,
        )
        raise RuntimeError(f"Auth routers failed to mount: {e}") from e
    else:
        # DEV/TEST: Warning explícito pero continuar (para tests parciales)
        logger.warning(
            "⚠️ Auth routers no montados (ENVIRONMENT=%s): %s",
            os.environ.get("ENVIRONMENT", "unset"),
            e,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN (internal routes sin /api prefix para consistencia con auth internal)
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.modules.admin.routes import get_admin_routers

    for r in get_admin_routers():
        # Routers con prefix /_internal van en public (sin /api) para consistencia
        # con auth internal que también vive en /_internal/...
        if r.prefix and r.prefix.startswith("/_internal"):
            _include_once(public, r, "admin", _mounted_public)
        else:
            # Routers sin /_internal van en api (con /api prefix)
            _include_once(api, r, "admin", _mounted_api)
except Exception as e:
    logger.exception("❌ Admin routers no montados (ver traceback): %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# PAYMENTS (LEGACY - ELIMINADO)
# ═══════════════════════════════════════════════════════════════════════════
# El módulo legacy 'payments' fue eliminado completamente.
# Todo el flujo de checkout, webhooks, acreditación de créditos, recibos
# e historial ahora pasa exclusivamente por el módulo 'billing'.
# Ver: app/modules/billing/


# ═══════════════════════════════════════════════════════════════════════════
# PROJECTS
# ═══════════════════════════════════════════════════════════════════════════
# NOTA: get_projects_router() crea una nueva instancia cada vez,
# por lo que no hay riesgo de duplicación por id.
try:
    from app.modules.projects.routes import get_projects_router

    # Instancias separadas para cada capa (diseño original preservado)
    projects_router_api = get_projects_router()
    projects_router_public = get_projects_router()

    _include_once(api, projects_router_api, "projects", _mounted_api)
    _include_once(public, projects_router_public, "projects", _mounted_public)
except Exception as e:
    # Log detallado con stacktrace para diagnóstico de errores de import
    logger.error(
        "❌ Projects routers no montados (ver traceback completo): %s",
        e,
        exc_info=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# FILES
# ═══════════════════════════════════════════════════════════════════════════
try:
    files_main_router = _try_import_router([
        "app.modules.files.routes.files_routes",
        "app.modules.files.routes",
    ])
    if files_main_router:
        _include_once(api, files_main_router, "files", _mounted_api)
        _include_once(public, files_main_router, "files", _mounted_public)
except Exception as e:
    logger.info("Router de Files no montado: %s", e)

# Files metrics ya están incluidos en files_routes.py bajo /files/metrics/*
# No se monta por separado para evitar duplicación

# ═══════════════════════════════════════════════════════════════════════════
# PROJECT FILE ACTIVITY (contrato frontend 2026-01-19)
# ═══════════════════════════════════════════════════════════════════════════
# Este router se monta por separado porque su prefix es /projects/{project_id}/file-activity
# y NO está incluido en files_routes.py que usa /files/* como prefix base.
try:
    from app.modules.files.routes.project_file_activity_routes import router as project_file_activity_router

    # Solo en API - requiere autenticación
    _include_once(api, project_file_activity_router, "project-file-activity", _mounted_api)
    logger.info("✅ Project File Activity router montado en /api/projects/{id}/file-activity")
except Exception as e:
    logger.warning("⚠ Router de Project File Activity no montado: %s", e)




# ═══════════════════════════════════════════════════════════════════════════
# RAG
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.modules.rag.routes import router as rag_main_router

    # RAG solo en public por ahora
    _include_once(public, rag_main_router, "rag", _mounted_public)
    logger.info("✅ Módulo RAG montado")
except Exception as e:
    logger.error("❌ Router de RAG no montado: %s", e, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# BILLING
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.modules.billing import router as billing_router

    # Billing solo en API
    _include_once(api, billing_router, "billing", _mounted_api)
    logger.info("✅ Módulo Billing montado")
except Exception as e:
    logger.warning("⚠ Router de Billing no montado: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# USER PROFILE (includes tax profile)
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.modules.user_profile.routes import combined_router as user_profile_combined_router

    # User Profile (combined with tax profile) solo en API (requiere autenticación)
    # Routes: /api/profile/*, /api/profile/tax-profile, etc.
    _include_once(api, user_profile_combined_router, "user_profile", _mounted_api)
    logger.info("✅ Módulo User Profile (con Tax Profile) montado")
except Exception as e:
    logger.warning("⚠ Router de User Profile no montado: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL EMAIL ROUTES
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.routes.internal_email_routes import router as internal_email_router

    _include_once(api, internal_email_router, "internal", _mounted_api)
    logger.info("✅ Endpoint interno de email montado")
except Exception as e:
    logger.debug("Endpoint interno de email no montado: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL DB DIAGNOSTICS (diagnóstico temporal)
# ═══════════════════════════════════════════════════════════════════════════
try:
    from app.routes.internal_db_ping_routes import router as internal_db_ping_router

    # Montar en AMBAS capas para acceso consistente:
    # - /api/_internal/db/ping (con prefix /api)
    # - /_internal/db/ping (sin prefix, root)
    _include_once(api, internal_db_ping_router, "internal-db-ping", _mounted_api)
    _include_once(public, internal_db_ping_router, "internal-db-ping", _mounted_public)
    logger.info("✅ Endpoint interno de DB ping montado (api + public)")
except Exception as e:
    logger.debug("Endpoint interno de DB ping no montado: %s", e)

try:
    from app.routes.internal_db_user_query_routes import router as internal_db_user_query_router

    # Montar en AMBAS capas para acceso consistente:
    # - /api/_internal/db/user-by-email (con prefix /api)
    # - /api/_internal/db/login-path-simulation (con prefix /api)
    # - /_internal/db/user-by-email (sin prefix, root)
    # - /_internal/db/login-path-simulation (sin prefix, root)
    _include_once(api, internal_db_user_query_router, "internal-db-user-query", _mounted_api)
    _include_once(public, internal_db_user_query_router, "internal-db-user-query", _mounted_public)
    logger.info("✅ Endpoints internos DB user-by-email + login-path-simulation montados (api + public)")
except Exception as e:
    # Diagnóstico temporal: usar error con exc_info para ver causa sin stacktrace completo
    logger.error("❌ Endpoints DB user-query NO montados: %s", e, exc_info=True)

try:
    from app.routes.internal_db_wallet_routes import router as internal_db_wallet_router

    # Montar en AMBAS capas:
    # - /api/_internal/db/wallet-model
    # - /_internal/db/wallet-model
    _include_once(api, internal_db_wallet_router, "internal-db-wallet", _mounted_api)
    _include_once(public, internal_db_wallet_router, "internal-db-wallet", _mounted_public)
    logger.info("✅ Endpoint interno DB wallet-model montado (api + public)")
except Exception as e:
    logger.debug("Endpoint interno de DB wallet-model no montado: %s", e)

try:
    from app.routes.internal_db_checkout_intent_routes import router as internal_db_checkout_intent_router

    # Montar en AMBAS capas:
    # - /api/_internal/db/checkout-intent-model
    # - /_internal/db/checkout-intent-model
    _include_once(api, internal_db_checkout_intent_router, "internal-db-checkout-intent", _mounted_api)
    _include_once(public, internal_db_checkout_intent_router, "internal-db-checkout-intent", _mounted_public)
    logger.info("✅ Endpoint interno DB checkout-intent-model montado (api + public)")
except Exception as e:
    logger.debug("Endpoint interno de DB checkout-intent-model no montado: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# DEBUG ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════
@api.get("/_debug/loaded-routers")
def loaded_routers():
    """
    Endpoint de debug para ver qué routers se montaron y en qué capa.
    
    Estructura de respuesta:
    - api: lista de routers montados en /api
    - public: lista de routers montados en /
    - all: lista completa con formato "{layer}:{module}.{name}"
    - counts: totales por capa
    - has_duplicates: True si hay entradas duplicadas (bug)
    - has_unknown: True si algún router no tiene tag definido (bug)
    """
    # Separar por capa
    api_routers = [entry for entry in _loaded if entry.startswith("/api:")]
    public_routers = [entry for entry in _loaded if entry.startswith("/:")]
    
    # Extraer solo nombres (sin prefijo de capa)
    api_names = [entry.split(":", 1)[1] for entry in api_routers]
    public_names = [entry.split(":", 1)[1] for entry in public_routers]
    
    # Detectar duplicados dentro de cada capa
    api_duplicates = [name for name in api_names if api_names.count(name) > 1]
    public_duplicates = [name for name in public_names if public_names.count(name) > 1]
    
    # Detectar routers sin tags ("unknown")
    unknown_routers = [entry for entry in _loaded if ".unknown" in entry or ".unnamed" in entry]
    
    return {
        "api": api_names,
        "public": public_names,
        "all": _loaded,
        "counts": {
            "api": len(_mounted_api),
            "public": len(_mounted_public),
            "total": len(_loaded),
        },
        "has_duplicates": bool(api_duplicates or public_duplicates),
        "duplicates": {
            "api": list(set(api_duplicates)),
            "public": list(set(public_duplicates)),
        },
        "has_unknown": bool(unknown_routers),
        "unknown_routers": unknown_routers,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTER FINAL
# ═══════════════════════════════════════════════════════════════════════════
router = APIRouter()
router.include_router(api)
router.include_router(public)

# Log resumen al final del montaje
logger.info(
    "📊 Routers montados: API=%d, Public=%d, Total=%d",
    len(_mounted_api),
    len(_mounted_public),
    len(_loaded),
)

# Fin del archivo backend/app/routes/master_routes.py
