from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/database.py

SQLAlchemy + asyncpg con conexión directa a PostgreSQL (puerto 5432).
TLS habilitado con verificación. Pool del lado del cliente (AsyncAdaptedQueuePool)
para reutilizar conexiones y reducir latencia.

Configuración actual (enero 2026):
- Conexión directa: db.<project_ref>.supabase.co:5432
- IPv4 add-on habilitado (compatible con Railway)
- Pool del cliente: AsyncAdaptedQueuePool (SQLAlchemy async)

Provee:
- engine (create_async_engine con pool adaptado)
- SessionLocal (async_sessionmaker)
- Base (DeclarativeBase con naming convention para Alembic)
- Dependencias FastAPI: get_async_session / get_db
- context manager: session_scope()
- check_database_health()

Notas:
- Se añaden timeouts a nivel de conexión (asyncpg: timeout, command_timeout).
- Se aplica SET SESSION statement_timeout al abrir cada sesión (configurable).
- Pool con pool_pre_ping=True valida conexiones antes de reusar.

DECISIÓN TÉCNICA (Postgres Direct + BD 2.0):
- NO se usa SET LOCAL statement_timeout por query individual (por consistencia).
- SET SESSION aplica configuración a nivel de sesión.
- Para timeouts específicos en endpoints críticos, usar asyncio.timeout() en el caller.
- statement_cache_size=0 se mantiene por compatibilidad con posibles proxies intermediarios.
"""

import os
import sys
import ssl
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus
from uuid import uuid4
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

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _prepared_statement_name_func,
        "server_settings": {"search_path": "public"},
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


async def _configure_session(session: AsyncSession) -> None:
    """
    Aplica configuraciones por sesión:
    - SET SESSION statement_timeout para limitar consultas "largas" en esta sesión.
    
    DECISIÓN TÉCNICA (Postgres Direct + BD 2.0):
    - SET SESSION aplica el timeout a nivel de sesión de forma confiable.
    - Para timeouts deterministas en endpoints críticos (login, projects list),
      usar asyncio.timeout() o asyncio.wait_for() en el caller como capa adicional.
    
    Estrategia de defensa en profundidad:
    1. SET SESSION como primera capa (configuración de sesión)
    2. asyncio.timeout() en callers críticos como segunda capa (determinista)
    3. Pool timeout (pool_timeout) como última línea de defensa
    """
    if SKIP_DB_INIT:
        return
    try:
        await session.execute(text(f"SET SESSION statement_timeout = {DB_SESSION_STATEMENT_TIMEOUT_MS}"))
    except Exception as e:
        logger.debug(f"[DB] No se pudo aplicar statement_timeout de sesión: {e}")


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
    "session_scope",
    "check_database_health",
    "log_db_identity",
    "init_db_diagnostics",
]
# Fin del archivo backend/app/shared/database/database.py
