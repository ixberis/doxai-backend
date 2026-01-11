from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/database.py

SQLAlchemy + asyncpg con conexión directa a PostgreSQL (puerto 5432).
TLS habilitado con verificación. Pool del lado del cliente (AsyncAdaptedQueuePool)
para reutilizar conexiones y reducir latencia.

═══════════════════════════════════════════════════════════════════════════════════
ARQUITECTURA DE INICIALIZACIÓN DE CONEXIÓN (enero 2026)
═══════════════════════════════════════════════════════════════════════════════════

OBJETIVO:
    Configurar cada conexión física del pool EXACTAMENTE UNA VEZ con:
    - statement_timeout (5000ms por defecto)
    - search_path (vía server_settings, ya manejado por asyncpg)

MECANISMO CANÓNICO:
    Usamos el evento de pool "connect" de SQLAlchemy sobre engine.sync_engine.
    Este evento se dispara UNA SOLA VEZ cuando se crea una nueva conexión física,
    no en cada checkout del pool.

    Para asyncpg, ejecutamos el SQL de inicialización usando:
        dbapi_connection.run_async(async_init_fn)

    El guard secundario usa connection_record.info["doxai_conn_init_done"] = True
    para garantizar idempotencia incluso si el evento se disparara dos veces.

FLUJO:
    1. Pool crea nueva conexión física → evento "connect" se dispara
    2. _on_connect() usa run_async() para ejecutar SET SESSION statement_timeout
    3. connection_record.info["doxai_conn_init_done"] = True
    4. Requests posteriores que reutilizan esa conexión → NO ejecutan nada

PER-REQUEST (LEGACY MODE):
    Si DB_APPLY_SESSION_TIMEOUT_PER_REQUEST=1:
    - El evento "connect" sigue aplicando statement_timeout
    - Pero _configure_session() RE-APLICA en cada request (para debugging)

DIAGNÓSTICO:
    Si DB_TIMEOUT_DIAGNOSTICS=1:
    - Log "conn_init_applied" con el timeout cuando se configura una nueva conexión
    - Log "SHOW statement_timeout" UNA VEZ por proceso para verificación

═══════════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import ssl
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, TYPE_CHECKING
from urllib.parse import quote_plus
from uuid import uuid4

from starlette.requests import Request as StarletteRequest
from app.shared.database.base import Base  # reutilizamos la Base única

# truststore puede no estar instalado en todos los entornos
try:
    import truststore  # type: ignore
except Exception:  # pragma: no cover
    truststore = None  # type: ignore

# certifi para CA bundle estable en contenedores
try:
    import certifi  # type: ignore
except Exception:  # pragma: no cover
    certifi = None  # type: ignore

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.shared.config import settings

# Windows event loop policy (debe configurarse antes de crear el engine)
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

logger = logging.getLogger("uvicorn.error")


# ── Helper para normalizar settings a str (maneja SecretStr, None, ints, etc.)
def _to_str_setting(value: object) -> str:
    """
    Normaliza un valor de settings a str:
    - Si es None → ""
    - Si tiene get_secret_value() (p.ej. SecretStr) → usa ese valor
    - En caso contrario, usa str(value)
    """
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return str(value)
    return str(value)


def _env_bool(name: str, default: bool) -> bool:
    """
    Lee un booleano desde env de forma robusta.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off"):
        return False
    return default


# ── Check if DB is disabled for tests (avoid blocking connections)
SKIP_DB_INIT = _env_bool("SKIP_DB_INIT", False)

# Default timeout (used when DB is initialized, or as fallback)
DB_SESSION_STATEMENT_TIMEOUT_MS: int = 5000

# Flag para aplicar SET SESSION per-request (fallback legacy, default=False en prod)
# En prod el timeout se aplica via pool event once-per-connection
DB_APPLY_SESSION_TIMEOUT_PER_REQUEST = _env_bool("DB_APPLY_SESSION_TIMEOUT_PER_REQUEST", False)

# Flag para fallback per-request si pool connect init falló
# Solo se usa si el init de conexión falló y se necesita recuperación operativa
DB_CONNECT_INIT_FALLBACK_PER_REQUEST = _env_bool("DB_CONNECT_INIT_FALLBACK_PER_REQUEST", False)

# Flag para diagnóstico temporal: loguea SHOW statement_timeout una vez por proceso
DB_TIMEOUT_DIAGNOSTICS = _env_bool("DB_TIMEOUT_DIAGNOSTICS", False)

# Guard global para diagnóstico (una vez por proceso)
_db_timeout_diagnostics_logged = False

# Flags globales de proceso para estado de pool connect init
# Usados por _configure_session para decidir si hacer fallback per-request
_CONNECT_INIT_FAILED = False
_connect_init_failed_logged = False  # Para loguear warning solo una vez
_CONNECT_INIT_SUCCEEDED_ONCE = False  # Evita quedarse "pegado" en fallback por fallo transitorio

if SKIP_DB_INIT:
    logger.warning("[DB] SKIP_DB_INIT=1: Database disabled (test mode)")
    engine = None  # type: ignore
    SessionLocal = None  # type: ignore
else:
    # ── Parámetros (valores desde settings) normalizados a str
    DB_USER = _to_str_setting(getattr(settings, "db_user", None))
    DB_PASSWORD = _to_str_setting(getattr(settings, "db_password", None))
    DB_HOST = _to_str_setting(getattr(settings, "db_host", None))          # db.<project_ref>.supabase.co
    DB_PORT = _to_str_setting(getattr(settings, "db_port", None))          # 5432 (Direct)
    DB_NAME = _to_str_setting(getattr(settings, "db_name", None))

    DB_ECHO_SQL = bool(getattr(settings, "db_echo_sql", False))

    # TLS habilitado por defecto, y verificable por flag
    DB_TLS_ENABLED = bool(getattr(settings, "db_tls", True))

    # ✅ NUEVO: permitir controlar verificación TLS por env o settings (Railway friendly)
    # - settings.db_tls_verify si existe
    # - env DB_TLS_VERIFY si está definido
    _db_tls_verify_default = bool(getattr(settings, "db_tls_verify", True))
    DB_TLS_VERIFY = _env_bool("DB_TLS_VERIFY", _db_tls_verify_default)

    # Timeouts configurables (segundos / milisegundos)
    DB_CONNECT_TIMEOUT_S: float = float(getattr(settings, "db_connect_timeout_s", 5.0))
    DB_COMMAND_TIMEOUT_S: float = float(getattr(settings, "db_command_timeout_s", 5.0))
    DB_SESSION_STATEMENT_TIMEOUT_MS = int(getattr(settings, "db_session_statement_timeout_ms", 5000))

    # ══════════════════════════════════════════════════════════════════════════
    # Pool del cliente (AsyncAdaptedQueuePool) hacia Postgres Direct
    # ══════════════════════════════════════════════════════════════════════════
    # - pool_size: conexiones permanentes en el pool del cliente
    # - max_overflow: conexiones adicionales temporales bajo carga
    # - pool_timeout: segundos máximos esperando una conexión del pool
    # - pool_recycle: segundos antes de reciclar conexiones (evita stale)
    # - pool_pre_ping: valida conexión antes de reusar (evita errores de conn cerrada)
    # ══════════════════════════════════════════════════════════════════════════
    DB_POOL_SIZE: int = int(getattr(settings, "db_pool_size", 5))
    DB_MAX_OVERFLOW: int = int(getattr(settings, "db_max_overflow", 5))
    DB_POOL_TIMEOUT: int = int(getattr(settings, "db_pool_timeout", 5))
    DB_POOL_RECYCLE: int = int(getattr(settings, "db_pool_recycle", 1800))
    DB_POOL_PRE_PING: bool = bool(getattr(settings, "db_pool_pre_ping", True))

    # DSN asyncpg para Postgres Direct (puerto 5432)
    ASYNC_DSN = (
        f"postgresql+asyncpg://"
        f"{quote_plus(DB_USER)}:"
        f"{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    log_level = logger.debug if DB_ECHO_SQL else logger.info
    log_level(
        f"[DB] Conectando a Postgres Direct → {DB_HOST}:{DB_PORT}/{DB_NAME} "
        f"(asyncpg, echo={DB_ECHO_SQL}, tls={DB_TLS_ENABLED}, tls_verify={DB_TLS_VERIFY}, "
        f"pool_size={DB_POOL_SIZE}, max_overflow={DB_MAX_OVERFLOW}, pool_pre_ping={DB_POOL_PRE_PING})"
    )


    def build_ssl_context() -> ssl.SSLContext:
        """
        Crea un SSLContext para conexiones TLS a Postgres Direct.

        Reglas:
          - Si DB_TLS_VERIFY = False:
              * usa contexto no verificado (CERT_NONE), sin hostname checks
              * útil para entornos donde se requiere conexión sin verificación
          - Si DB_TLS_VERIFY = True:
              * verificación estricta con CA bundle estable (certifi si está disponible)
              * fallback a truststore si existe; o create_default_context si no
        """
        if not DB_TLS_VERIFY:
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        # Verificación estricta
        if certifi is not None:
            ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=certifi.where())
        elif truststore is not None:
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # type: ignore[arg-type]
        else:
            ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx


    # Construir ssl_context solo si TLS está habilitado
    ssl_context = build_ssl_context() if DB_TLS_ENABLED else None


    # ── Engine con AsyncAdaptedQueuePool (pool cliente hacia Postgres Direct)
    def _prepared_statement_name_func() -> str:
        return f"__asyncpg_{uuid4().hex[:8]}__"


    # NOTA: statement_cache_size=0 se mantiene por compatibilidad con proxies intermediarios
    # y como medida de seguridad ante cambios futuros de infraestructura.
    #
    # NOTA: statement_timeout NO se pone en server_settings porque no es confiable
    # en asyncpg. Se aplica via pool event "connect" con run_async().
    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _prepared_statement_name_func,
        "server_settings": {
            "search_path": "public",
        },
        "timeout": DB_CONNECT_TIMEOUT_S,
        "command_timeout": DB_COMMAND_TIMEOUT_S,
    }

    if DB_TLS_ENABLED and ssl_context is not None:
        connect_args["ssl"] = ssl_context

    # ══════════════════════════════════════════════════════════════════════════
    # Pool interno del async engine con parámetros configurables
    # - El async engine usa AsyncAdaptedQueuePool por defecto (no se puede
    #   especificar poolclass=QueuePool explícitamente)
    # - pool_pre_ping=True valida conexión antes de checkout
    # - statement_cache_size=0 mantenido por compatibilidad (decisión actual)
    # ══════════════════════════════════════════════════════════════════════════
    engine = create_async_engine(
        ASYNC_DSN,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=DB_POOL_RECYCLE,
        pool_pre_ping=DB_POOL_PRE_PING,
        echo=DB_ECHO_SQL,
        execution_options={"prepared_statement_cache_size": 0},
        connect_args=connect_args,
    )

    # Verificación objetiva del pool class real (no asumir por nombre)
    actual_pool = engine.sync_engine.pool
    pool_class_name = actual_pool.__class__.__name__
    logger.info(
        f"[DB] Pool active: class={pool_class_name} "
        f"pool_size={DB_POOL_SIZE} max_overflow={DB_MAX_OVERFLOW} "
        f"pool_timeout={DB_POOL_TIMEOUT} recycle={DB_POOL_RECYCLE} pre_ping={DB_POOL_PRE_PING}"
    )
    if pool_class_name == "NullPool":
        logger.warning("[DB] ⚠️ NullPool detected - connection reuse DISABLED")

    # ══════════════════════════════════════════════════════════════════════════
    # INICIALIZACIÓN CANÓNICA DE CONEXIÓN VIA POOL EVENT
    # ══════════════════════════════════════════════════════════════════════════
    #
    # El evento "connect" se dispara UNA SOLA VEZ cuando el pool crea una nueva
    # conexión física. Usamos connection_record.info como SSOT para el guard.
    #
    # Para ejecutar SQL async desde un evento sync, usamos el método run_async()
    # del AdaptedConnection de SQLAlchemy. Este método recibe un CALLABLE que
    # será invocado con la conexión asyncpg real, no un coroutine ya creado.
    #
    # Patrón canónico:
    #   dbapi_conn.run_async(lambda async_conn: async_conn.execute(sql))
    # ══════════════════════════════════════════════════════════════════════════

    def _on_connect(dbapi_connection, connection_record):
        """
        Pool event handler: se ejecuta cuando se crea una NUEVA conexión física.
        
        Este evento NO se dispara en cada checkout, solo al crear conexiones.
        Usamos connection_record.info como guard para idempotencia.
        
        Args:
            dbapi_connection: El AdaptedConnection de SQLAlchemy (wrapper de asyncpg)
            connection_record: El ConnectionPoolEntry del pool
        """
        global _CONNECT_INIT_FAILED, _CONNECT_INIT_SUCCEEDED_ONCE
        
        # Guard con connection_record.info (SSOT canónico)
        if connection_record.info.get("doxai_conn_init_done"):
            return
        
        timeout_ms = DB_SESSION_STATEMENT_TIMEOUT_MS
        
        # run_async() recibe un CALLABLE, no un coroutine ya construido.
        # El callable recibe la conexión asyncpg real como argumento.
        def _init(async_conn):
            return async_conn.execute(f"SET SESSION statement_timeout = {timeout_ms}")
        
        try:
            dbapi_connection.run_async(_init)
            
            # Marcar como inicializado solo si tuvo éxito
            connection_record.info["doxai_conn_init_done"] = True
            connection_record.info.pop("doxai_conn_init_error", None)
            
            # Marcar que al menos una conexión tuvo éxito (evita fallback permanente)
            _CONNECT_INIT_SUCCEEDED_ONCE = True
            
            if DB_TIMEOUT_DIAGNOSTICS:
                logger.info(
                    "[DB] [DIAG] conn_init_applied statement_timeout=%dms",
                    timeout_ms
                )
        except Exception as e:
            # NO marcar init_done si falló - registrar el error
            connection_record.info["doxai_conn_init_error"] = str(e)
            # Setear flag global para que _configure_session pueda hacer fallback
            _CONNECT_INIT_FAILED = True
            logger.warning("[DB] pool connect init failed: %s", e)

    # Registrar el evento en el sync_engine (requerido para pool events)
    event.listen(engine.sync_engine, "connect", _on_connect)
    logger.info(
        "[DB] Pool event 'connect' registered: statement_timeout=%dms will be applied once per physical connection",
        DB_SESSION_STATEMENT_TIMEOUT_MS
    )

    # ── Registrar statement counter global (para diagnóstico A/B) ──
    try:
        from app.shared.database.statement_counter import setup_statement_counter
        setup_statement_counter(engine.sync_engine)
    except Exception as e:
        logger.debug(f"[DB] Statement counter not registered: {e}")

    SessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False,
    )

    # Log de startup
    if DB_APPLY_SESSION_TIMEOUT_PER_REQUEST:
        logger.info(
            "[DB] DB_APPLY_SESSION_TIMEOUT_PER_REQUEST=True: SET SESSION will ALSO run per-request (legacy/debug mode)"
        )
    else:
        logger.info(
            "[DB] statement_timeout = %d ms via pool event 'connect' (canonical mode, per-request is NO-OP)",
            DB_SESSION_STATEMENT_TIMEOUT_MS
        )


# ══════════════════════════════════════════════════════════════════════════════
# PER-REQUEST CONFIGURATION (legacy mode only)
# ══════════════════════════════════════════════════════════════════════════════
# En modo canonical (default), _configure_session es NO-OP porque el timeout
# ya está aplicado via pool event.
#
# En legacy mode (DB_APPLY_SESSION_TIMEOUT_PER_REQUEST=1), ejecuta SET SESSION
# en cada request para debugging o compatibilidad.
# ══════════════════════════════════════════════════════════════════════════════

async def _maybe_log_statement_timeout(session: AsyncSession, mode: str = "canonical") -> None:
    """
    Diagnóstico temporal: loguea SHOW statement_timeout UNA VEZ por proceso.
    
    Solo activo si DB_TIMEOUT_DIAGNOSTICS=1.
    
    Args:
        session: La sesión de base de datos
        mode: El modo de aplicación ("canonical", "legacy", "fallback")
    """
    global _db_timeout_diagnostics_logged
    
    if not DB_TIMEOUT_DIAGNOSTICS or _db_timeout_diagnostics_logged:
        return
    
    try:
        result = await session.execute(text("SHOW statement_timeout"))
        val = result.scalar_one_or_none()
        logger.info("[DB] [DIAG] SHOW statement_timeout = %s mode=%s (verified per-process)", val, mode)
        _db_timeout_diagnostics_logged = True
    except Exception:
        logger.debug("[DB] [DIAG] SHOW statement_timeout failed", exc_info=True)
        _db_timeout_diagnostics_logged = True


async def _configure_session(session: AsyncSession) -> None:
    """
    Configuración per-request de la sesión.
    
    ARQUITECTURA (enero 2026):
    
    CANONICAL MODE (default):
        - El statement_timeout ya está aplicado via pool event "connect"
        - Esta función es NO-OP (~0ms)
        - Solo ejecuta diagnóstico si DB_TIMEOUT_DIAGNOSTICS=1
    
    LEGACY MODE (DB_APPLY_SESSION_TIMEOUT_PER_REQUEST=1):
        - Ejecuta SET SESSION statement_timeout en cada request
        - Para debugging o troubleshooting
        - Añade ~60-180ms de latencia
    
    FALLBACK MODE (DB_CONNECT_INIT_FALLBACK_PER_REQUEST=1 + _CONNECT_INIT_FAILED + not _CONNECT_INIT_SUCCEEDED_ONCE):
        - Si el pool connect init falló globalmente Y ninguna conexión tuvo éxito
        - Flag global _CONNECT_INIT_FAILED se setea cuando _on_connect falla
        - Flag _CONNECT_INIT_SUCCEEDED_ONCE evita quedarse "pegado" tras fallo transitorio
        - Operativo solo como recuperación de emergencia
    
    Esto permite que rutas críticas como /api/projects/active-projects
    tengan dep.db_configure_ms ~0-3ms en steady state.
    """
    global _connect_init_failed_logged
    
    if SKIP_DB_INIT:
        return
    
    # LEGACY MODE: ejecutar SET SESSION per-request siempre
    if DB_APPLY_SESSION_TIMEOUT_PER_REQUEST:
        try:
            await session.execute(text(f"SET SESSION statement_timeout = {DB_SESSION_STATEMENT_TIMEOUT_MS}"))
            await _maybe_log_statement_timeout(session, mode="legacy")
        except Exception as e:
            logger.debug("[DB] Error en SET SESSION (legacy mode): %s", e)
        return
    
    # FALLBACK MODE: si pool connect init falló globalmente, fallback habilitado,
    # Y ninguna conexión ha tenido éxito aún (evita quedarse pegado por fallo transitorio)
    if _CONNECT_INIT_FAILED and not _CONNECT_INIT_SUCCEEDED_ONCE and DB_CONNECT_INIT_FALLBACK_PER_REQUEST:
        # Loguear warning solo una vez para no spamear
        if not _connect_init_failed_logged:
            logger.warning(
                "[DB] pool connect init failed globally, applying statement_timeout per-request (fallback mode)"
            )
            _connect_init_failed_logged = True
        
        try:
            await session.execute(text(f"SET SESSION statement_timeout = {DB_SESSION_STATEMENT_TIMEOUT_MS}"))
            await _maybe_log_statement_timeout(session, mode="fallback")
        except Exception as e:
            logger.debug("[DB] Error en SET SESSION (fallback mode): %s", e)
        return
    
    # CANONICAL MODE: NO-OP, solo diagnóstico opcional
    await _maybe_log_statement_timeout(session, mode="canonical")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database not initialized (SKIP_DB_INIT=1)")
    async with SessionLocal() as session:
        await _configure_session(session)
        try:
            yield session
        except (OperationalError, SQLAlchemyError):
            try:
                await session.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database not initialized (SKIP_DB_INIT=1)")
    async with SessionLocal() as session:
        await _configure_session(session)
        try:
            yield session
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass


async def get_db_timed(request: StarletteRequest) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para obtener sesión DB con instrumentación granular.
    
    Mide un segmento crítico para diagnóstico de latencia:
    - dep.db_configure_ms: tiempo de _configure_session
    
    En CANONICAL MODE (default), _configure_session es NO-OP, por lo que
    dep.db_configure_ms será ~0-3ms (solo overhead de medición).
    
    En LEGACY MODE, incluye el SET SESSION (~60-180ms).
    
    El total se guarda en request.state.db_dep_total_ms (NO en dep_timings)
    para evitar doble conteo en TimingMiddleware.deps_ms.
    
    Uso:
        @router.get("/...")
        async def my_route(
            request: Request,
            db: AsyncSession = Depends(get_db_timed),
        ): ...
    """
    from app.shared.observability.dep_timing import record_dep_timing
    
    if SessionLocal is None:
        raise RuntimeError("Database not initialized (SKIP_DB_INIT=1)")
    
    session = SessionLocal()
    async with session:
        # Fase: Configure session (en canonical mode es NO-OP)
        configure_start = time.perf_counter()
        await _configure_session(session)
        configure_ms = (time.perf_counter() - configure_start) * 1000
        record_dep_timing(request, "dep.db_configure_ms", configure_ms)
        
        # Total guardado como atributo separado (NO en dep_timings para evitar doble conteo)
        # Robustez para mocks: verificar que state existe
        state = getattr(request, "state", None)
        if state is not None:
            state.db_dep_total_ms = configure_ms
        
        try:
            yield session
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass


@asynccontextmanager
async def session_scope(configure: bool = True) -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database not initialized (SKIP_DB_INIT=1)")
    async with SessionLocal() as session:
        if configure:
            await _configure_session(session)
        try:
            yield session
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass


# Alias para uso en jobs
get_async_session_context = session_scope


async def check_database_health(timeout_s: float = 3.0, sql: str = "SELECT 1") -> bool:
    """
    Verifica conectividad a la base de datos.
    """
    if engine is None:
        return False
    try:
        async with asyncio.timeout(timeout_s):
            async with engine.connect() as conn:
                await conn.execute(text(sql))
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DB identity diagnostics for Railway/Supabase
# ══════════════════════════════════════════════════════════════════════════════
#
# PROPÓSITO:
#   Diagnóstico temporal para identificar la DB real a la que está conectada la
#   app cuando hay sospechas de mismatch entre Railway y Supabase (Direct).
#
# USO:
#   - Por defecto NO se ejecuta (evita ruido en logs de producción).
#   - Para activarlo, definir en Railway: DB_IDENTITY_DIAGNOSTICS=1
#   - Se ejecuta UNA vez al startup y loguea con prefijo [DB-IDENTITY].
#
# CUÁNDO ACTIVAR:
#   - Sospechas de conexión a DB incorrecta
#   - Errores "relation does not exist" inexplicables
#   - Verificación post-migración de entorno
#
# NOTA: Este es diagnóstico temporal, NO monitoreo permanente.
# ══════════════════════════════════════════════════════════════════════════════

# Flag para habilitar diagnóstico (default: deshabilitado)
DB_IDENTITY_DIAGNOSTICS_ENABLED = _env_bool("DB_IDENTITY_DIAGNOSTICS", False)


async def log_db_identity() -> None:
    """
    Ejecuta una consulta de diagnóstico para identificar la DB real a la que
    está conectada la app. Loguea con prefijo [DB-IDENTITY] para fácil búsqueda
    en Railway/logs.

    COMPORTAMIENTO:
      - Solo se ejecuta si DB_IDENTITY_DIAGNOSTICS=1 está definido en el entorno.
      - Si el flag no está activo, retorna silenciosamente sin hacer nada.
      - Usa logger.info() para el diagnóstico (nunca ERROR).
      - Si falla, loguea como debug y continúa sin romper el arranque.

    ACTIVACIÓN EN RAILWAY:
      Definir variable de entorno: DB_IDENTITY_DIAGNOSTICS=1

    NOTA: Este es diagnóstico temporal para troubleshooting, no monitoreo permanente.
    """
    # Verificar flag explícito primero
    if not _env_bool("DB_IDENTITY_DIAGNOSTICS", False):
        return

    if engine is None:
        logger.debug("[DB-IDENTITY] Database disabled (SKIP_DB_INIT=1), skipping diagnostics")
        return

    # Normalizar env para logging informativo
    env = os.getenv("ENVIRONMENT") or os.getenv("PYTHON_ENV") or "development"
    env = env.strip().strip('"').strip("'").lower()

    logger.info("[DB-IDENTITY] Diagnóstico habilitado (DB_IDENTITY_DIAGNOSTICS=1), env=%s", env)

    diagnostic_sql = text("""
        SELECT
            current_database() AS db,
            current_schema() AS schema,
            current_setting('search_path') AS search_path,
            inet_server_addr()::text AS server_ip,
            inet_server_port()::text AS server_port,
            to_regclass('public.app_users')::text AS public_app_users,
            to_regclass('public.account_activations')::text AS public_account_activations
    """)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(diagnostic_sql)
            row = result.mappings().fetchone()

        if row:
            logger.info(
                "[DB-IDENTITY] db=%s schema=%s search_path=%s server_ip=%s server_port=%s "
                "public_app_users=%s public_account_activations=%s",
                row.get("db"),
                row.get("schema"),
                row.get("search_path"),
                row.get("server_ip"),
                row.get("server_port"),
                row.get("public_app_users"),
                row.get("public_account_activations"),
            )
        else:
            logger.info("[DB-IDENTITY] Query ejecutada pero sin resultado (row=None)")

    except Exception as exc:
        # No romper el arranque; loguear como debug para no contaminar logs
        logger.debug("[DB-IDENTITY] Error ejecutando diagnóstico", exc_info=True)


async def init_db_diagnostics() -> None:
    """
    Hook de inicialización para ejecutar diagnósticos de DB al arranque.
    Llamar desde app/main.py en el lifespan o startup.

    COMPORTAMIENTO:
      - Seguro llamarlo siempre (no hace nada si DB_IDENTITY_DIAGNOSTICS no está activo).
      - Nunca aborta el arranque de la aplicación.
      - Cualquier excepción se atrapa y loguea como debug.

    ACTIVACIÓN:
      Definir en Railway: DB_IDENTITY_DIAGNOSTICS=1
    """
    try:
        await log_db_identity()
    except Exception as exc:
        # Nunca romper startup por diagnóstico
        logger.debug("[DB-IDENTITY] Excepción inesperada en init_db_diagnostics: %s", exc)


__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_async_session",
    "get_async_session_context",
    "get_db",
    "get_db_timed",
    "session_scope",
    "check_database_health",
    "log_db_identity",
    "init_db_diagnostics",
    "DB_SESSION_STATEMENT_TIMEOUT_MS",
    "DB_APPLY_SESSION_TIMEOUT_PER_REQUEST",
]
# Fin del archivo backend/app/shared/database/database.py
