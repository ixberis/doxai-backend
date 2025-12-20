
# -*- coding: utf-8 -*-
"""
backend/app/main.py

Punto de entrada principal del backend DoxAI.

Ajustes clave:
- Uso de app.core.settings como fachada de configuración.
- Montaje de observabilidad Prometheus (/metrics) vía app.observability.prom
- Scheduler con job de limpieza de cachés (cache_cleanup_hourly).
- Compatibilidad Windows con asyncio.WindowsSelectorEventLoopPolicy
- Warm-up y ciclo de vida con limpieza segura en shutdown
- Health principal /health delegado al paquete app.routes (health_routes.py)

Autor: Ixchel Beristain
Fecha: 17/11/2025
"""

from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"   # backend/.env
load_dotenv(dotenv_path=ENV_PATH, override=False)


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

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
# Normalizar env tolerando comillas y espacios (ej. "staging" → staging)
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().strip('"').strip("'").lower()
_override_env = _ENVIRONMENT != "production"
load_dotenv(dotenv_path=_ENV_PATH, override=_override_env)

logging.getLogger(__name__).info(
    f"[dotenv] Loaded {_ENV_PATH} (override={_override_env}, ENVIRONMENT={_ENVIRONMENT})"
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import anyio

# ---------------------------------------------------------------------------
# Configuración: usamos la fachada de core.settings, con fallback seguro
# ---------------------------------------------------------------------------
try:
    from app.core.settings import get_settings
except Exception as _cfg_err:
    logging.getLogger(__name__).warning(
        f"[config] get_settings no disponible ({_cfg_err}). Usando defaults de DEV."
    )

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


import asyncio as _asyncio

logging.getLogger("uvicorn.error").info(
    f"[LoopPolicy] {type(_asyncio.get_event_loop_policy()).__name__}"
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _safe_log(level: int, msg: str):
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

        # NOTA:
        # El job de refresco de métricas de Auth se delega a la capa de
        # métricas del módulo Auth o se habilitará en una fase posterior.
        # Aquí evitamos acoplar main.py a detalles de implementación de DB.

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
                    
            except Exception as e:
                logger.error(f"❌ Error durante shutdown ordenado: {e}")

        logger.info("🔴 Backend de DoxAI apagado.")


openapi_tags = [
    {
        "name": "Authentication",
        "description": "Registro, Login, Refresh tokens y Activación de cuenta",
    },
    {"name": "User Profile", "description": "Perfil de usuario y suscripción"},
    {"name": "Files", "description": "Gestión de archivos"},
    {"name": "Projects", "description": "Gestión de proyectos"},
    {"name": "RAG", "description": "Indexación y análisis"},
    {"name": "Payments", "description": "Pagos, webhooks y créditos"},
]

app = FastAPI(
    title="DoxAI API",
    description="API unificada para DoxAI",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
)

# CORS - Configuración robusta para preflight OPTIONS
# ═══════════════════════════════════════════════════════════════════════════════
# REGLAS:
# 1. En PRODUCTION: CORS_ORIGINS DEBE venir de env var; si falta → CORS cerrado
# 2. En DEVELOPMENT: fallback permisivo a localhost
# 3. "*" con allow_credentials=True es inválido → se filtra
# ═══════════════════════════════════════════════════════════════════════════════
settings = get_settings()
_is_production = _ENVIRONMENT == "production"

# Obtener origins de configuración
if hasattr(settings, "get_cors_origins"):
    origins_list = settings.get_cors_origins()
else:
    origins_raw = getattr(settings, "allowed_origins", "")
    origins_list = [o.strip() for o in origins_raw.split(",") if o.strip()]

# Sanitizar: "*" con credentials=True es inválido en navegadores
# Filtrar "*" y mantener solo origins explícitos
if "*" in origins_list:
    origins_list = [o for o in origins_list if o != "*"]
    if not origins_list:
        # Solo tenía "*", ahora está vacío
        pass  # Se manejará abajo

# Determinar origins finales según ambiente
if not origins_list:
    if _is_production:
        # PRODUCCIÓN SIN CORS_ORIGINS = ERROR CRÍTICO
        logger.error(
            "❌ CORS_ORIGINS missing in production; CORS disabled. "
            "Configure CORS_ORIGINS env var with explicit origins."
        )
        origins_list = []  # CORS cerrado - ningún origen permitido
    else:
        # DESARROLLO: fallback permisivo a localhost
        logger.warning(
            "⚠️ CORS_ORIGINS no configurado en desarrollo. "
            "Usando fallback: localhost:5173, localhost:3000, localhost:8080"
        )
        origins_list = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8080",
        ]

logger.info(f"🌐 CORS origins configurados ({_ENVIRONMENT}): {origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=600,  # Cache preflight por 10 minutos
)

# Observabilidad Prometheus (/metrics)
setup_observability(app)

# Exception handler for rate limiting (consistent 429 response)
from app.shared.security.rate_limit_dep import RateLimitExceeded, rate_limit_response

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """Ensure RateLimitExceeded always returns consistent 429 JSON response."""
    return rate_limit_response(
        retry_after=exc.retry_after,
        message=str(exc.detail),
    )

# Incluye router maestro
from app.routes import router as main_router  # import dentro del scope

app.include_router(main_router)


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


if __name__ == "__main__":
    is_production = os.getenv("PYTHON_ENV") == "production"
    disable_reload_env = os.getenv("DISABLE_RELOAD", "").lower() in (
        "true",
        "1",
        "yes",
    )
    dev_reload = os.getenv("DEV_RELOAD") == "1"
    enable_reload = not is_production and not disable_reload_env and not dev_reload

    logging.getLogger(__name__).info(
        f"🔧 Starting server with reload={enable_reload} (production={is_production})"
    )

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
