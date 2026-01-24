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

# Logging base (temprano) - usa setup_logging para aplicar config de multipart
from app.shared.config.logging_config import setup_logging, get_multipart_logger_states

# Determinar nivel y formato según entorno
_log_level = "DEBUG" if _ENVIRONMENT != "production" else "INFO"
_log_fmt = "json" if _ENVIRONMENT == "production" else "plain"
setup_logging(level=_log_level, fmt=_log_fmt)

logger = logging.getLogger(__name__)

# Verificación de estado de loggers multipart en startup (print a stderr - no depende de logging)
for state in get_multipart_logger_states():
    msg = (
        f"MULTIPART_LOGGER_STATE name={state['name']} "
        f"level={state['level']} effective_level={state['effective_level']} "
        f"propagate={state['propagate']} handlers={state['handlers_count']}"
    )
    print(msg, file=sys.stderr)

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

# ─────────────────────────────────────────────────────────────────────────────
# METRICS INITIALIZATION: Moved to lifespan() for controlled startup
# See lifespan() function below - initialize_all_metrics() runs there
# ─────────────────────────────────────────────────────────────────────────────

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
    """
    Gate para warmup de recursos LEGACY (modelos/tesseract/httpx).
    
    Este gate es INDEPENDIENTE de _should_warmup_startup() (infraestructura).
    Controla solo run_warmup_once() para recursos de procesamiento.
    
    NO logea "omitido" para evitar confusión con startup warmups.
    
    Returns:
        True si el warmup de recursos legacy debe ejecutarse.
    """
    dev_reload = os.getenv("DEV_RELOAD") == "1"
    skip_on_reload = os.getenv("SKIP_WARMUP_ON_RELOAD", "1") == "1"
    force_warmup = os.getenv("FORCE_WARMUP") == "1"

    if force_warmup:
        logger.info("🔥 FORCE_WARMUP=1 - ejecutando warm-up forzado")
        return True
    if dev_reload and skip_on_reload:
        logger.debug("⚡ Modo reload detectado - omitiendo warm-up de recursos")
        return False

    settings = get_settings()
    return bool(getattr(settings, "WARMUP_ENABLE", False))


def _should_warmup_startup() -> bool:
    """
    Gate UNIFICADO para warmups de startup (DB, Redis, Login Cache).
    
    Este gate controla TODOS los warmups de infraestructura que hacen network I/O.
    
    Rules (en orden de prioridad):
    1. STARTUP_WARMUP_DISABLED=1 → NO warmup (máxima prioridad)
    2. PYTEST_CURRENT_TEST presente → NO warmup (tests NUNCA hacen I/O)
    3. SKIP_DB_INIT=1 → NO warmup (indica entorno de test explícito)
    4. STARTUP_WARMUP_ENABLED=1 → SÍ warmup (override explícito)
    5. ENVIRONMENT=production → SÍ warmup (default en prod)
    6. Cualquier otro caso → NO warmup (default seguro)
    
    Returns:
        True si los warmups de startup deben ejecutarse.
    """
    # 1. Disable explícito (máxima prioridad)
    if os.getenv("STARTUP_WARMUP_DISABLED", "0").lower() in ("1", "true", "yes"):
        logger.debug("startup_warmup_gate: disabled via STARTUP_WARMUP_DISABLED=1")
        return False
    
    # 2. Tests NUNCA hacen warmup (pytest inyecta esta variable)
    if os.getenv("PYTEST_CURRENT_TEST"):
        logger.debug("startup_warmup_gate: disabled via PYTEST_CURRENT_TEST")
        return False
    
    # 3. SKIP_DB_INIT indica entorno de test/CI
    if os.getenv("SKIP_DB_INIT", "0").lower() in ("1", "true", "yes"):
        logger.debug("startup_warmup_gate: disabled via SKIP_DB_INIT=1")
        return False
    
    # 4. Enable explícito (para forzar warmup fuera de prod)
    if os.getenv("STARTUP_WARMUP_ENABLED", "0").lower() in ("1", "true", "yes"):
        logger.debug("startup_warmup_gate: enabled via STARTUP_WARMUP_ENABLED=1")
        return True
    
    # 5. Producción hace warmup por defecto
    env = os.getenv("ENVIRONMENT", "development").lower().strip()
    if env == "production":
        logger.debug("startup_warmup_gate: enabled via ENVIRONMENT=production")
        return True
    
    # 6. Default: NO warmup (seguro para dev/staging/test)
    logger.debug("startup_warmup_gate: disabled by default (ENVIRONMENT=%s)", env)
    return False


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
    logger.info("lifespan_startup: FastAPI lifespan starting")
    
    # ─────────────────────────────────────────────────────────────────────────
    # PROMETHEUS METRICS INITIALIZATION (first thing in startup)
    # Must run before any other startup code to ensure metrics are registered
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.observability.metrics_init import initialize_all_metrics
        from prometheus_client import REGISTRY
        
        logger.info("metrics_init: starting Prometheus metrics initialization")
        
        init_result = initialize_all_metrics()
        
        files_ok = init_result.get("files_delete", False)
        touch_ok = init_result.get("touch_debounce", False)
        db_ok = init_result.get("db_metrics", False)
        success_count = sum(1 for v in init_result.values() if v)
        total_count = len(init_result)
        
        logger.info(
            "metrics_init_complete: %d/%d collectors (files_delete=%s touch_debounce=%s db_metrics=%s)",
            success_count,
            total_count,
            files_ok,
            touch_ok,
            db_ok,
        )
        
        # Diagnostic: verify metrics are in REGISTRY
        # Try _names_to_collectors first, fallback to iterating samples
        names_to_collectors = getattr(REGISTRY, "_names_to_collectors", None)
        
        if names_to_collectors is not None:
            # Fast path: use internal dict
            has_files_delete = "files_delete_total" in names_to_collectors
            has_files_latency = "files_delete_latency_seconds" in names_to_collectors
            has_touch = "touch_debounced_allowed_total" in names_to_collectors
            has_doxai = "doxai_ghost_files_count" in names_to_collectors
            registered_names_sample = list(names_to_collectors.keys())[:30]
        else:
            # Fallback: iterate REGISTRY.collect() and extract exact names
            all_metric_names = set()
            for family in REGISTRY.collect():
                all_metric_names.add(family.name)
                for sample in family.samples:
                    all_metric_names.add(sample.name)
            
            has_files_delete = "files_delete_total" in all_metric_names
            has_files_latency = "files_delete_latency_seconds" in all_metric_names
            has_touch = "touch_debounced_allowed_total" in all_metric_names
            has_doxai = "doxai_ghost_files_count" in all_metric_names
            registered_names_sample = list(all_metric_names)[:30]
        
        registry_families = len(list(REGISTRY.collect()))
        
        logger.info(
            "metrics_init_registry_check: families=%d has_files_delete_total=%s has_files_delete_latency_seconds=%s has_touch_debounced_allowed_total=%s has_doxai_ghost_files_count=%s",
            registry_families,
            has_files_delete,
            has_files_latency,
            has_touch,
            has_doxai,
        )
        
        # If any metric not found, log sample for debugging
        if not (has_files_delete and has_files_latency and has_touch and has_doxai):
            logger.warning(
                "metrics_init_missing_metrics: registered_names_sample=%s",
                registered_names_sample,
            )
    except Exception as e:
        logger.error("metrics_init_failed: %s", e, exc_info=True)
    
    # Registrar relaciones ORM cross-module (auth <-> payments)
    # Esto debe ocurrir antes de cualquier uso de las relaciones
    try:
        from app.shared.orm import register_cross_module_relationships
        register_cross_module_relationships()
    except Exception as e:
        logger.warning(f"⚠️ Error registrando ORM cross-module relationships: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # CRITICAL: Log CheckoutIntent ORM mapper at startup for SSOT diagnostics
    # This helps identify if user_id is still present in the deployed code
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.routes.internal_db_checkout_intent_routes import log_checkout_intent_mapper_at_startup
        log_checkout_intent_mapper_at_startup()
    except Exception as e:
        logger.warning(f"⚠️ CheckoutIntent mapper logging failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN NOTIFICATION EMAIL CONFIG LOGGING (SSOT: ADMIN_NOTIFICATION_EMAIL)
    # Log masked status for observability. DO NOT log the actual email address.
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.shared.services.admin_email_config import get_admin_notification_email
        admin_email = get_admin_notification_email()
        if admin_email:
            # Mask: show only first 3 chars + domain
            at_idx = admin_email.find("@")
            if at_idx > 3:
                masked = admin_email[:3] + "***" + admin_email[at_idx:]
            else:
                masked = "***" + admin_email[at_idx:] if at_idx > 0 else "***"
            logger.info("🔔 Admin notification email configured: %s (admin_notification_email_configured=true)", masked)
        else:
            logger.warning("⚠️ Admin notification email NOT configured (admin_notification_email_configured=false). Set ADMIN_NOTIFICATION_EMAIL env var.")
    except Exception as e:
        logger.warning(f"⚠️ Admin email config check failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # LEGACY RESOURCE WARMUP (modelos/tesseract/httpx)
    # Gated by _should_warmup() - independiente del warmup de infraestructura
    # NO logear "omitido" para evitar confusión con startup warmups
    # ─────────────────────────────────────────────────────────────────────────
    try:
        if _should_warmup():
            logger.info("🌡️ Ejecutando warm-up de recursos legacy...")
            await run_warmup_once()
            logger.info("✅ Warm-up de recursos legacy completado")
        # else: silencio - no es relevante si los recursos legacy no se calientan
    except Exception as e:
        logger.warning(f"⚠️ Error en warm-up de recursos legacy: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # STARTUP WARMUPS (DB, Redis, Login Cache)
    # All gated by _should_warmup_startup() to prevent I/O during tests
    # ─────────────────────────────────────────────────────────────────────────
    if _should_warmup_startup():
        logger.info("🌡️ Startup warmups iniciando...")
        
        # DB warmup (pool/TLS/primera query)
        try:
            from app.shared.database.db_warmup import warmup_db_async
            db_result = await warmup_db_async()
            if db_result.success:
                if db_result.skipped:
                    logger.info("🗄️ DB warmup omitido (SKIP_DB_INIT)")
                else:
                    logger.info(
                        "🗄️ DB warmup completado: duration_ms=%.2f",
                        db_result.duration_ms,
                    )
            else:
                logger.warning(
                    "⚠️ DB warmup falló: error=%s duration_ms=%.2f",
                    db_result.error,
                    db_result.duration_ms,
                )
        except Exception as e:
            logger.warning(f"⚠️ DB warmup no disponible: {e}")

        # Redis warmup (rate limiter connection + LUA scripts)
        try:
            from app.shared.security.redis_warmup import warmup_redis_async
            redis_result = await warmup_redis_async()
            if redis_result.success:
                logger.info(
                    "🔴 Redis warmup completado: scripts=%d duration_ms=%.2f",
                    redis_result.scripts_loaded,
                    redis_result.duration_ms,
                )
            # Don't log warning for expected "not configured" case
        except Exception as e:
            logger.warning(f"⚠️ Redis warmup no disponible: {e}")

        # Login cache warmup (best-effort, no real data)
        try:
            from app.shared.security.login_cache_warmup import warmup_login_cache_async
            login_cache_result = await warmup_login_cache_async()
            if login_cache_result.success:
                logger.info(
                    "🔑 Login cache warmup completado: redis=%s pipeline=%s duration_ms=%.2f",
                    login_cache_result.redis_connected,
                    login_cache_result.pipeline_tested,
                    login_cache_result.duration_ms,
                )
            elif login_cache_result.error:
                logger.debug(
                    "🔑 Login cache warmup skipped: %s",
                    login_cache_result.error,
                )
        except Exception as e:
            logger.debug(f"🔑 Login cache warmup no disponible: {e}")
        
        logger.info("🌡️ Startup warmups completados")
    else:
        logger.debug("⚡ Startup warmups omitidos (gate returned False)")

    # HTTP Metrics Store startup
    _http_metrics_store = None
    try:
        from app.shared.observability import get_http_metrics_store, HTTPMetricsMiddleware
        from app.shared.database import SessionLocal
        
        _http_metrics_store = get_http_metrics_store()
        _http_metrics_store.set_session_factory(SessionLocal)
        await _http_metrics_store.start()
        
        # Store reference in app state for shutdown
        app.state.http_metrics_store = _http_metrics_store
        logger.info("📊 HTTP Metrics Store iniciado")
    except Exception as e:
        logger.warning(f"⚠️ HTTP Metrics Store no disponible: {e}")

    # DB identity diagnostics (Railway/Supabase mismatch debugging)
    try:
        from app.shared.database import init_db_diagnostics
        await init_db_diagnostics()
    except Exception as e:
        logger.warning(f"⚠️ DB diagnostics no disponible: {e}")

    # Iniciar scheduler y registrar jobs (skip if SKIP_DB_INIT for tests)
    _skip_scheduler = os.getenv("SKIP_DB_INIT", "0").lower() in ("1", "true", "yes")
    if not _skip_scheduler:
        try:
            from app.shared.scheduler import get_scheduler

            scheduler = get_scheduler()

            # Job 1: limpieza de caché (si existe)
            try:
                from app.shared.scheduler.jobs import register_cache_cleanup_job
                register_cache_cleanup_job(scheduler)
            except Exception as e:
                logger.debug(f"Cache cleanup job no disponible: {e}")

            # Job 2: expiración de checkout intents
            try:
                from app.modules.billing.jobs import register_expire_intents_job
                register_expire_intents_job()
            except Exception as e:
                logger.debug(f"Expire intents job no disponible: {e}")

            # Job 3: reconciliación de archivos fantasma
            # Usa env vars: FILES_RECONCILE_GHOSTS_ENABLED, FILES_RECONCILE_GHOSTS_INTERVAL_HOURS
            try:
                from app.modules.files.jobs.reconcile_ghost_files_job import register_reconcile_ghost_files_job
                register_reconcile_ghost_files_job(scheduler)
            except Exception as e:
                logger.debug(f"Reconcile ghost files job no disponible: {e}")

            # Job 4: refresco de métricas DB → Prometheus
            # Usa env vars: DB_METRICS_REFRESH_ENABLED, DB_METRICS_REFRESH_INTERVAL_SECONDS
            _db_refresh_enabled = os.getenv("DB_METRICS_REFRESH_ENABLED", "1")
            _db_refresh_interval = os.getenv("DB_METRICS_REFRESH_INTERVAL_SECONDS", "60")
            logger.info(
                "db_metrics_refresh_register_attempt: enabled=%s interval=%s",
                _db_refresh_enabled,
                _db_refresh_interval,
            )
            try:
                from app.shared.scheduler.jobs.db_metrics_refresh_job import (
                    register_db_metrics_refresh_job,
                    bootstrap_db_metrics_refresh,
                )
                register_db_metrics_refresh_job(scheduler)
                logger.info("db_metrics_refresh_job_registered: success=true")
            except Exception as e:
                logger.warning("db_metrics_refresh_job_failed: error=%s", e, exc_info=True)
                bootstrap_db_metrics_refresh = None  # type: ignore

            scheduler.start()
            logger.info("⏰ Scheduler iniciado con jobs programados")
            
            # Bootstrap: ejecutar refresh inmediato después de que el scheduler arranca
            if bootstrap_db_metrics_refresh is not None:
                import asyncio
                asyncio.create_task(bootstrap_db_metrics_refresh())
        except Exception as e:
            logger.warning(f"⚠️ No se pudo iniciar scheduler: {e}")
    else:
        logger.debug("⏰ Scheduler omitido (SKIP_DB_INIT)")

    logger.info("🟢 Backend de DoxAI iniciado.")
    try:
        yield
    finally:
        # ────────── SHUTDOWN ──────────
        logger.info("🔴 Iniciando shutdown ordenado...")
        with anyio.CancelScope(shield=True):
            try:
                # Detener scheduler primero (only if it was started)
                if not _skip_scheduler:
                    try:
                        from app.shared.scheduler import get_scheduler

                        scheduler = get_scheduler()
                        scheduler.shutdown(wait=True)
                        logger.info("⏰ Scheduler detenido")
                    except Exception as e:
                        logger.warning(f"⚠️ Error deteniendo scheduler: {e}")
                
                # HTTP Metrics Store shutdown
                try:
                    if hasattr(app.state, "http_metrics_store") and app.state.http_metrics_store:
                        await app.state.http_metrics_store.stop()
                        logger.info("📊 HTTP Metrics Store detenido")
                except Exception as e:
                    logger.warning(f"⚠️ Error deteniendo HTTP Metrics Store: {e}")

                logger.info("🚫 Cancelling active analysis jobs...")
                # Use shorter timeout for graceful shutdown (2s for tests, 30s for prod)
                _job_timeout = 2.0 if _skip_scheduler else 30.0
                await job_registry.cancel_all_tasks(timeout=_job_timeout)

                # PayPal clients cleanup (legacy payments module removed)
                # No action needed - billing uses Stripe only

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
# LIVENESS ENDPOINT - Railway healthcheck (MUST be first, before any middleware)
# ═══════════════════════════════════════════════════════════════════════════════
from fastapi.responses import PlainTextResponse


@app.get("/healthz", include_in_schema=False, response_class=PlainTextResponse)
async def healthz_liveness():
    """
    Pure liveness probe for Railway/Kubernetes.
    
    - Always returns 200 OK if the process is alive
    - NO database, Redis, auth, or any external dependency
    - Works during cold start
    - Bypasses all heavy middleware
    """
    return PlainTextResponse("ok", status_code=200)

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
        # En producción: solo regex si está explícitamente configurado
        # En desarrollo: fallback a Vercel regex para comodidad
        if is_production:
            allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX") or None
        else:
            allow_origin_regex = os.getenv(
                "CORS_ALLOW_ORIGIN_REGEX",
                r"^https://.*\.vercel\.app$",
            )
    else:
        # Lista explícita de origins
        # En producción: solo regex si está explícitamente configurado (fail-closed)
        # En desarrollo: fallback a Vercel regex para previews
        if is_production:
            allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX") or None
        else:
            allow_origin_regex = os.getenv(
                "CORS_ALLOW_ORIGIN_REGEX",
                r"^https://.*\.vercel\.app$",
            )

    # En desarrollo: auto-agregar dominios de producción para comodidad de testing
    # En producción: fail-closed, solo lo que venga de CORS_ORIGINS (no auto-add)
    if not is_wildcard_only and not is_production:
        dev_convenience_origins = ["https://app.doxai.site", "https://doxai.site"]
        for origin in dev_convenience_origins:
            if origin not in origins_list:
                origins_list.append(origin)

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
    logger.info(f"  allow_origin_regex:   {allow_origin_regex!r}")
    logger.info(f"  allow_credentials:    {allow_credentials}")
    logger.info(f"  allow_methods:        {allow_methods}")
    logger.info(f"  allow_headers:        {allow_headers}")
    logger.info(f"  CORS ACTIVE:          {bool(origins_list) or bool(allow_origin_regex)}")
    logger.info("=" * 70)

    if not origins_list and not allow_origin_regex:
        logger.error("🚫 CORS IS DISABLED - No origins will be allowed!")
    elif allow_origin_regex:
        logger.info(f"✅ CORS ENABLED for {len(origins_list)} origin(s) + regex pattern")
    else:
        logger.info(f"✅ CORS ENABLED for {len(origins_list)} origin(s)")

    app_instance.add_middleware(CORSMiddleware, **cors_config)
    return cors_config


# Observabilidad Prometheus (/metrics)
# IMPORTANTE: el orden real de ejecución de middlewares en Starlette es inverso al registro.
# Registramos CORS AL FINAL para que se ejecute PRIMERO (outermost).
setup_observability(app)

# Timing middleware para diagnóstico de latencia
try:
    from app.shared.middleware.timing_middleware import TimingMiddleware
    app.add_middleware(TimingMiddleware)
    logger.info("⏱️ Timing middleware habilitado")
except Exception as e:
    logger.warning(f"⚠️ Timing middleware no disponible: {e}")

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
        # Files - download selected (causa de 404 en producción 2026-01-21)
        "/api/files/{project_id}/download-selected",
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


# ═══════════════════════════════════════════════════════════════════════════════
# LOG INTERNAL DB ROUTES (diagnóstico obligatorio para /_internal/db/*)
# ═══════════════════════════════════════════════════════════════════════════════
def _log_internal_db_routes():
    """
    Loguea TODAS las rutas que contienen '/_internal/db' al startup.
    Siempre activo para verificar runtime en Railway (no depende de OpenAPI).
    
    Recorre recursivamente todos los routers anidados para capturar paths completos.
    """
    from starlette.routing import Mount, Route
    from fastapi.routing import APIRoute
    
    internal_db_routes = []
    
    def _collect_routes(routes, prefix=""):
        for route in routes:
            if isinstance(route, APIRoute):
                # FastAPI APIRoute: concatenar prefix actual + route.path
                full_path = f"{prefix}{route.path}".replace("//", "/")
                if "/_internal/db" in full_path:
                    methods = ",".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
                    internal_db_routes.append((full_path, methods, route.name or "?"))
            elif isinstance(route, Mount):
                # Starlette Mount (incluyendo APIRouter montado)
                mount_prefix = f"{prefix}{route.path}".replace("//", "/")
                if hasattr(route, "routes"):
                    _collect_routes(route.routes, mount_prefix)
                # También revisar si es un APIRouter con .app
                if hasattr(route, "app") and hasattr(route.app, "routes"):
                    _collect_routes(route.app.routes, mount_prefix)
            elif hasattr(route, "routes"):
                # Router genérico con sub-routes
                sub_prefix = f"{prefix}{getattr(route, 'path', '')}".replace("//", "/")
                _collect_routes(route.routes, sub_prefix)
    
    _collect_routes(app.routes)
    
    # Log siempre, incluso si está vacío (para diagnóstico)
    logger.info("=" * 70)
    logger.info("🔧 INTERNAL DB ROUTES CHECK (/_internal/db/*)")
    logger.info("=" * 70)
    
    if internal_db_routes:
        for path, methods, name in sorted(internal_db_routes):
            logger.info(f"  internal_db_route_mounted path={path} methods={methods} name={name}")
        logger.info(f"  Total: {len(internal_db_routes)} routes")
    else:
        logger.error("❌ NO INTERNAL DB ROUTES FOUND! Possible causes:")
        logger.error("   - Import error in master_routes.py (check logs above)")
        logger.error("   - Router not included in api/public layers")
        logger.error("   - internal_db_user_query_routes.py has syntax error")
    
    logger.info("=" * 70)

_log_internal_db_routes()


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
