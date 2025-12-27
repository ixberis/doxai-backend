# -*- coding: utf-8 -*-
"""
backend/app/main.py

Punto de entrada principal del backend DoxAI.

Ajustes clave:
- Uso de app.core.settings como fachada de configuración.
- Montaje de observabilidad Prometheus (/metrics) vía app.observability.prom
- Scheduler con job de limpieza de cachés (cache_cleanup_hourly)
- Compatibilidad Windows con asyncio.WindowsSelectorEventLoopPolicy
- Warm-up y ciclo de vida con limpieza segura en shutdown
- Health principal /health delegado al paquete app.routes (health_routes.py)
- CORS robusto: allow_origins + allow_origin_regex para *.vercel.app

Autor: Ixchel Beristain
Fecha: 17/11/2025
"""

import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import os
import atexit
from contextlib import asynccontextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# Cargar .env ANTES de cualquier import que use os.getenv
# En DEV: override=True para que .env mande sobre variables del entorno
# En PROD: override=False para respetar variables del entorno (Railway, etc.)
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().strip('"').strip("'").lower()
_override_env = _ENVIRONMENT != "production"
load_dotenv(dotenv_path=_ENV_PATH, override=_override_env)

# Logging base (temprano)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

logger.info(f"[dotenv] Loaded {_ENV_PATH} (override={_override_env}, ENVIRONMENT={_ENVIRONMENT})")
logger.info(f"[LoopPolicy] {type(asyncio.get_event_loop_policy()).__name__}")

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import anyio

# ---------------------------------------------------------------------------
# Configuración: usamos la fachada de core.settings, con fallback seguro
# ---------------------------------------------------------------------------
try:
    from app.core.settings import get_settings
except Exception as _cfg_err:
    logger.warning(f"[config] get_settings no disponible ({_cfg_err}). Usando defaults de DEV.")

    class _FallbackSettings:
        WARMUP_ENABLE = False
        allowed_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:3000",
        )
        host = "0.0.0.0"
        port = 8000

    def get_settings():
        return _FallbackSettings()


from app.observability.prom import setup_observability

# Warmup/recursos (fallbacks)
try:
    from app.shared.core.resource_cache import (
        run_warmup_once,
        get_warmup_status,
        shutdown_all,
    )
except Exception:
    async def run_warmup_once():
        ...

    def get_warmup_status():
        class _S:
            started_at = None
            ended_at = None
            duration_sec = None
            fast_ok = True
            hires_ok = True
            table_model_ok = True
            http_client_ok = True
            tesseract_ok = True
            errors = []
            is_ready = True

        return _S()

    async def shutdown_all():
        ...


try:
    from app.shared.utils.pdf_resource_manager import force_cleanup_all_pdf_resources
except Exception:
    def force_cleanup_all_pdf_resources():
        ...


try:
    from app.shared.utils.temp_directory_manager import (
        force_cleanup_all_temp_directories,
        cleanup_quarantine_directory,
    )
except Exception:
    def force_cleanup_all_temp_directories():
        ...

    def cleanup_quarantine_directory(max_age_hours: int = 1):
        ...


try:
    from app.shared.utils.async_job_registry import job_registry
except Exception:
    class _JR:
        async def cancel_all_tasks(self, timeout: float = 30.0):
            ...

    job_registry = _JR()


def _safe_log(level: int, msg: str):
    """
    Log seguro para evitar errores al cerrar streams durante shutdown/atexit.
    """
    try:
        has_open_stream = False
        for h in logger.handlers:
            stream = getattr(h, "stream", None)
            if stream is None or getattr(stream, "closed", False):
                continue
            has_open_stream = True
            break
        if has_open_stream and logger.isEnabledFor(level):
            logger.log(level, msg)
    except Exception:
        pass


def _should_warmup() -> bool:
    dev_reload = os.getenv("DEV_RELOAD") == "1"
    skip_on_reload = os.getenv("SKIP_WARMUP_ON_RELOAD", "1") == "1"
    force_warmup = os.getenv("FORCE_WARMUP") == "1"

    if force_warmup:
        logger.info("🔥 FORCE_WARMUP=1 - ejecutando warm-up forzado")
        return True
    if dev_reload and skip_on_reload:
        logger.debug("⚡ Modo reload detectado - omitiendo warm-up")
        return False

    settings = get_settings()
    return bool(getattr(settings, "WARMUP_ENABLE", False))


def atexit_cleanup():
    _safe_log(logging.DEBUG, "🔄 Running atexit cleanup...")
    try:
        force_cleanup_all_pdf_resources()
        force_cleanup_all_temp_directories()
    except Exception as e:
        _safe_log(logging.DEBUG, f"⚠️ Error in atexit cleanup: {e}")


atexit.register(atexit_cleanup)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ────────── STARTUP ──────────
    
    # Registrar relaciones ORM cross-module (auth <-> payments)
    # Esto debe ocurrir antes de cualquier uso de las relaciones
    try:
        from app.shared.orm import register_cross_module_relationships
        register_cross_module_relationships()
    except Exception as e:
        logger.warning(f"⚠️ Error registrando ORM cross-module relationships: {e}")
    
    try:
        if _should_warmup():
            logger.info("🌡️ Ejecutando warm-up de recursos...")
            await run_warmup_once()
        else:
            logger.info("⚡ Warm-up omitido")
    except Exception as e:
        logger.error(f"❌ Error en warm-up: {e}")

    # DB identity diagnostics (Railway/Supabase mismatch debugging)
    try:
        from app.shared.database import init_db_diagnostics
        await init_db_diagnostics()
    except Exception as e:
        logger.warning(f"⚠️ DB diagnostics no disponible: {e}")

    # Iniciar scheduler y registrar jobs
    try:
        from app.shared.scheduler import get_scheduler

        scheduler = get_scheduler()

        # Job 1: limpieza (si existe)
        try:
            from app.shared.scheduler.jobs import register_cache_cleanup_job
            register_cache_cleanup_job(scheduler)
        except Exception as e:
            logger.debug(f"Cache cleanup job no disponible: {e}")

        scheduler.start()
        logger.info("⏰ Scheduler iniciado con jobs programados")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo iniciar scheduler: {e}")

    logger.info("🟢 Backend de DoxAI iniciado.")
    try:
        yield
    finally:
        # ────────── SHUTDOWN ──────────
        logger.info("🔴 Iniciando shutdown ordenado...")
        with anyio.CancelScope(shield=True):
            try:
                # Detener scheduler primero
                try:
                    from app.shared.scheduler import get_scheduler

                    scheduler = get_scheduler()
                    scheduler.shutdown(wait=True)
                    logger.info("⏰ Scheduler detenido")
                except Exception as e:
                    logger.warning(f"⚠️ Error deteniendo scheduler: {e}")

                logger.info("🚫 Cancelling active analysis jobs...")
                await job_registry.cancel_all_tasks(timeout=30.0)

                # Cerrar clientes HTTP de PayPal
                try:
                    from app.modules.payments.services.webhooks.signature_verification import (
                        close_paypal_http_clients,
                    )
                    await close_paypal_http_clients()
                    logger.info("💳 Clientes HTTP de PayPal cerrados")
                except Exception as e:
                    logger.warning(f"⚠️ Error cerrando clientes PayPal: {e}")

                # Cierre de recursos cacheados
                try:
                    await shutdown_all()
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"❌ Error durante shutdown ordenado: {e}")

        logger.info("🔴 Backend de DoxAI apagado.")


openapi_tags = [
    {"name": "Authentication", "description": "Registro, Login, Refresh tokens y Activación de cuenta"},
    {"name": "User Profile", "description": "Perfil de usuario y suscripción"},
    {"name": "Files", "description": "Gestión de archivos"},
    {"name": "Projects", "description": "Gestión de proyectos"},
    {"name": "RAG", "description": "Indexación y análisis"},
    {"name": "Payments", "description": "Pagos, webhooks y créditos"},
]

# ═══════════════════════════════════════════════════════════════════════════════
# UTF-8 JSON Response Class (Opción A - más limpia)
# ═══════════════════════════════════════════════════════════════════════════════
from app.shared.utils.json_response import UTF8JSONResponse

app = FastAPI(
    title="DoxAI API",
    description="API unificada para DoxAI",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    default_response_class=UTF8JSONResponse,  # Fuerza charset=utf-8 en todas las respuestas JSON (return {...})
)

# ═══════════════════════════════════════════════════════════════════════════════
# CORS - Configuración robusta para preflight OPTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def _configure_cors(app_instance: FastAPI) -> dict:
    """
    Configura CORS middleware de forma verificable.

    Returns:
        dict con la configuración aplicada para logging.
    """
    # FAST PATH: Test mode con wildcard puro (bypass completo)
    if os.getenv("CORS_TEST_WILDCARD") == "1":
        logger.warning("🧪 CORS_TEST_WILDCARD=1: Usando config wildcard pura para tests")
        cors_config = {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "max_age": 600,
        }
        app_instance.add_middleware(CORSMiddleware, **cors_config)
        return cors_config

    settings = get_settings()

    # Detectar ambiente
    env_name = _ENVIRONMENT
    python_env = os.getenv("PYTHON_ENV", "NOT_SET")
    is_production = env_name == "production" or python_env == "production"

    # =========================================================================
    # FAIL-CLOSED EN PRODUCCIÓN: Solo usar CORS_ORIGINS explícito de env
    # =========================================================================
    cors_origins_raw = os.getenv("CORS_ORIGINS", "").strip()
    
    # Log inmediato para debug
    logger.info(f"🔍 CORS DEBUG: cors_origins_raw='{cors_origins_raw}', is_production={is_production}")
    
    # En producción: SOLO usar lo que viene de CORS_ORIGINS env var (fail-closed)
    # En desarrollo: permitir fallback a settings
    if is_production:
        # PRODUCCIÓN: fail-closed - solo env var explícita
        if not cors_origins_raw:
            # CORS DESHABILITADO en producción sin configuración explícita
            logger.error(
                "❌ CORS DISABLED: No CORS_ORIGINS env var in production! "
                "Set CORS_ORIGINS env var (e.g., CORS_ORIGINS=https://app.doxai.site). "
                "All cross-origin requests will be BLOCKED."
            )
            # NO añadir middleware CORS = todas las requests cross-origin fallarán
            return {
                "cors_disabled": True,
                "reason": "No CORS_ORIGINS configured in production (fail-closed)",
                "allow_origins": [],
            }
        
        # Verificar wildcard en producción
        if cors_origins_raw == "*":
            if os.getenv("ALLOW_CORS_WILDCARD_IN_PROD") == "1":
                logger.warning(
                    "⚠️ CORS WILDCARD IN PRODUCTION: Explicitly allowed via ALLOW_CORS_WILDCARD_IN_PROD=1. "
                    "This is a security risk!"
                )
            else:
                logger.error(
                    "❌ REFUSING WILDCARD CORS IN PRODUCTION! "
                    "Set explicit origins or ALLOW_CORS_WILDCARD_IN_PROD=1 to override."
                )
                return {
                    "cors_disabled": True,
                    "reason": "Wildcard CORS rejected in production (security)",
                    "allow_origins": [],
                }
        
        origins_list = [o.strip().strip('"').strip("'") for o in cors_origins_raw.split(",") if o.strip()]
    else:
        # DESARROLLO: permitir fallback a settings
        settings_origins = getattr(settings, "allowed_origins", "")
        origins_raw = cors_origins_raw or settings_origins
        
        if hasattr(settings, "get_cors_origins") and cors_origins_raw:
            origins_list = [o.strip().strip('"').strip("'") for o in origins_raw.split(",") if o.strip()]
        elif hasattr(settings, "get_cors_origins"):
            origins_list = settings.get_cors_origins()
        else:
            origins_list = [o.strip() for o in origins_raw.split(",") if o.strip()]
        
        # Fallback localhost en desarrollo si no hay origins
        if not origins_list:
            logger.warning("⚠️ CORS: No origins configured in development. Using localhost fallback.")
            origins_list = [
                "http://localhost:5173",
                "http://localhost:3000",
                "http://localhost:8080",
            ]

    allow_credentials = True
    allow_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    allow_headers = ["*"]
    allow_origin_regex = None

    # Detectar si es wildcard puro
    is_wildcard_only = (len(origins_list) == 1 and origins_list[0] == "*")
    
    logger.info(f"🔍 CORS DEBUG: origins_list={origins_list}, is_wildcard_only={is_wildcard_only}")
    
    # "*" con allow_credentials=True es inválido en navegadores
    if is_wildcard_only:
        logger.warning(
            "⚠️ CORS WILDCARD MODE: origins='*' detectado. "
            "Configurando allow_credentials=False y allow_methods=['*'] para permitir cualquier origen."
        )
        allow_credentials = False
        allow_methods = ["*"]
        allow_headers = ["*"]
        # allow_origin_regex ya es None
    elif "*" in origins_list:
        # Mezcla de "*" con otros - filtrar el "*"
        logger.warning("⚠️ CORS: Filtrando '*' de origins porque hay otros origins explícitos.")
        origins_list = [o for o in origins_list if o != "*"]
        allow_origin_regex = os.getenv(
            "CORS_ALLOW_ORIGIN_REGEX",
            r"^https://.*\.vercel\.app$",
        )
    else:
        # Lista explícita de origins
        allow_origin_regex = os.getenv(
            "CORS_ALLOW_ORIGIN_REGEX",
            r"^https://.*\.vercel\.app$",
        )

    # Asegurar dominios prod (SOLO si NO es wildcard puro y estamos en prod)
    if not is_wildcard_only and is_production:
        production_origins = ["https://app.doxai.site", "https://doxai.site"]
        for prod_origin in production_origins:
            if prod_origin not in origins_list:
                origins_list.append(prod_origin)

    # Construir config - NO incluir allow_origin_regex si es None (wildcard mode)
    cors_config = {
        "allow_origins": origins_list,
        "allow_credentials": allow_credentials,
        "allow_methods": allow_methods,
        "allow_headers": allow_headers,
        "expose_headers": ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
        "max_age": 600,
    }
    
    # Solo agregar regex si está definido (no en wildcard mode)
    if allow_origin_regex:
        cors_config["allow_origin_regex"] = allow_origin_regex

    logger.info("=" * 70)
    logger.info("🌐 CORS CONFIGURATION STARTUP")
    logger.info("=" * 70)
    logger.info(f"  ENVIRONMENT:          {env_name}")
    logger.info(f"  PYTHON_ENV:           {python_env}")
    logger.info(f"  is_production:        {is_production}")
    logger.info(f"  is_wildcard_only:     {is_wildcard_only}")
    logger.info(f"  CORS_ORIGINS (raw):   '{cors_origins_raw}' (env var)")
    logger.info(f"  origins_parsed:       {origins_list}")
    logger.info(f"  allow_origin_regex:   '{allow_origin_regex}'")
    logger.info(f"  allow_credentials:    {allow_credentials}")
    logger.info(f"  allow_methods:        {allow_methods}")
    logger.info(f"  allow_headers:        {allow_headers}")
    logger.info(f"  CORS ACTIVE:          {bool(origins_list) or bool(allow_origin_regex)}")
    logger.info("=" * 70)

    if not origins_list and not allow_origin_regex:
        logger.error("🚫 CORS IS DISABLED - No origins will be allowed!")
    else:
        logger.info(f"✅ CORS ENABLED for {len(origins_list)} origin(s) + regex pattern")

    app_instance.add_middleware(CORSMiddleware, **cors_config)
    return cors_config


# Observabilidad Prometheus (/metrics)
# IMPORTANTE: el orden real de ejecución de middlewares en Starlette es inverso al registro.
# Registramos CORS AL FINAL para que se ejecute PRIMERO (outermost).
setup_observability(app)

# CORS middleware - se registra al final para ejecutarse primero
_cors_config = _configure_cors(app)

# ═══════════════════════════════════════════════════════════════════════════════
# EXCEPTION HANDLERS CON UTF-8
# ═══════════════════════════════════════════════════════════════════════════════
from app.shared.security.rate_limit_dep import RateLimitExceeded, rate_limit_response
from app.shared.utils.json_response import json_response_utf8


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """Ensure RateLimitExceeded always returns consistent 429 JSON response with UTF-8."""
    return rate_limit_response(
        retry_after=exc.retry_after,
        message=str(exc.detail),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom HTTPException handler that ensures UTF-8 charset on JSON responses.

    Fixes mojibake in error messages (acentos).
    """
    return json_response_utf8(
        content={"detail": exc.detail},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


# Incluye router maestro
from app.routes import router as main_router

app.include_router(main_router)

# ═══════════════════════════════════════════════════════════════════════════════
# LOG RUTAS CRÍTICAS (diagnóstico 404 en producción)
# ═══════════════════════════════════════════════════════════════════════════════
def _log_critical_routes():
    """
    Log rutas críticas al startup para diagnóstico.
    Solo se ejecuta si LOG_CRITICAL_ROUTES=1.
    """
    if os.getenv("LOG_CRITICAL_ROUTES", "0") != "1":
        logger.info("📋 Critical routes logging disabled (set LOG_CRITICAL_ROUTES=1 to enable)")
        return
    
    critical_paths = [
        # Profile (causa de 500/404)
        "/api/profile",
        "/api/profile/profile",
        "/api/profile/subscription",
        # Projects (causa de 422 en producción)
        "/api/projects/active-projects",
        "/api/projects/closed-projects",
        "/api/projects/ready",
    ]
    
    # Collect all registered routes with full paths
    # ROBUST: Only recurse for Mount objects, APIRoute already has final path
    from starlette.routing import Mount
    
    registered_routes = set()
    
    def _collect_routes(routes, prefix=""):
        for route in routes:
            path = getattr(route, "path", "")
            
            if hasattr(route, "methods"):
                # APIRoute: path is already the full path from FastAPI
                registered_routes.add(route.path)
            elif isinstance(route, Mount):
                # Only Mount needs prefix concatenation for nested routes
                mount_prefix = f"{prefix}{path}".replace("//", "/")
                if hasattr(route, "routes"):
                    _collect_routes(route.routes, mount_prefix)
    
    _collect_routes(app.routes)
    
    logger.info("=" * 70)
    logger.info("🔍 CRITICAL ROUTES CHECK")
    logger.info("=" * 70)
    
    missing = []
    for path in critical_paths:
        found = path in registered_routes
        status = "✅" if found else "❌ MISSING"
        logger.info(f"  {status}: {path}")
        if not found:
            missing.append(path)
    
    if missing:
        logger.error(f"⚠️ {len(missing)} critical route(s) NOT REGISTERED: {missing}")
    else:
        logger.info("✅ All critical routes registered")
    
    logger.info("=" * 70)

_log_critical_routes()


# Health básicos de conveniencia (no duplican /health de health_routes.py)
@app.get("/")
async def root():
    return {"service": "DoxAI Backend", "status": "active"}


@app.get("/api/health/live")
async def health_live():
    return {"live": True}


@app.get("/api/health/ready")
async def health_ready():
    try:
        status = get_warmup_status()
        return {
            "started_at": status.started_at,
            "ended_at": status.ended_at,
            "duration_sec": status.duration_sec,
            "fast_ok": status.fast_ok,
            "hires_ok": status.hires_ok,
            "table_model_ok": status.table_model_ok,
            "http_client_ok": status.http_client_ok,
            "tesseract_ok": status.tesseract_ok,
            "errors": status.errors,
            "ready": status.is_ready,
        }
    except Exception:
        return {"ready": True}


@app.get("/api/_internal/routes")
async def list_all_routes(request: Request):
    """
    Debug endpoint para listar todas las rutas registradas.
    
    SECURITY GATING:
    - Production: requires ENABLE_INTERNAL_ROUTES_DEBUG=1 AND correct X-Internal-Debug-Key header
    - Non-production: requires ENABLE_INTERNAL_ROUTES_DEBUG=1 (no header needed)
    
    Returns 404 if not enabled (to avoid leaking endpoint existence).
    """
    is_prod = _ENVIRONMENT == "production"
    debug_enabled = os.getenv("ENABLE_INTERNAL_ROUTES_DEBUG", "0") == "1"
    
    if not debug_enabled:
        # Return 404 to not leak existence
        raise HTTPException(status_code=404, detail="Not Found")
    
    if is_prod:
        # In production, also require secret header
        expected_key = os.getenv("INTERNAL_DEBUG_KEY", "")
        provided_key = request.headers.get("X-Internal-Debug-Key", "")
        
        if not expected_key or provided_key != expected_key:
            # Return 404 to not leak existence
            raise HTTPException(status_code=404, detail="Not Found")
        
        logger.info("🔓 Internal routes debug accessed with valid key in production")
    else:
        logger.debug("🔓 Internal routes debug accessed (non-production)")
    
    # ROBUST: Only recurse for Mount objects, APIRoute already has final path
    from starlette.routing import Mount
    
    routes = []
    
    def _collect(route_list, prefix=""):
        for route in route_list:
            path = getattr(route, "path", "")
            methods = list(getattr(route, "methods", [])) if hasattr(route, "methods") else None
            name = getattr(route, "name", None)
            
            if methods:
                # APIRoute: path is already the full path from FastAPI
                routes.append({
                    "path": route.path,
                    "methods": methods,
                    "name": name,
                })
            elif isinstance(route, Mount):
                # Only Mount needs prefix concatenation for nested routes
                mount_prefix = f"{prefix}{path}".replace("//", "/")
                if hasattr(route, "routes"):
                    _collect(route.routes, mount_prefix)
    
    _collect(app.routes)
    
    # Sort by path
    routes.sort(key=lambda r: r["path"])
    
    # Critical routes check
    critical = [
        "/api/profile",
        "/api/profile/profile",
        "/api/projects/active-projects",
        "/api/projects/closed-projects",
    ]
    
    critical_status = {}
    all_paths = {r["path"] for r in routes}
    for c in critical:
        critical_status[c] = c in all_paths
    
    return {
        "total": len(routes),
        "critical_status": critical_status,
        "routes": routes,
    }


if __name__ == "__main__":
    settings = get_settings()

    is_production = os.getenv("PYTHON_ENV") == "production"
    disable_reload_env = os.getenv("DISABLE_RELOAD", "").lower() in ("true", "1", "yes")
    dev_reload = os.getenv("DEV_RELOAD") == "1"
    enable_reload = not is_production and not disable_reload_env and not dev_reload

    logger.info(f"🔧 Starting server with reload={enable_reload} (production={is_production})")

    reload_excludes = (
        [
            "debug_webhooks/*",
            "*.log",
            "*.tmp",
            "temp/*",
            "/tmp/*",
            "__pycache__/*",
            "*.pyc",
            ".git/*",
            "tests/*",
            "**/cache/**",
            "app/assets/**",
            "**/*.md",
        ]
        if enable_reload
        else None
    )

    uvicorn.run(
        "app.main:app",
        host=getattr(settings, "host", "0.0.0.0"),
        port=int(getattr(settings, "port", 8000)),
        reload=enable_reload,
        reload_excludes=reload_excludes,
        reload_delay=1.0 if enable_reload else None,
    )

# Fin del archivo backend/app/main.py
