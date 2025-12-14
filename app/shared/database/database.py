
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/database.py

SQLAlchemy + asyncpg detrás de PgBouncer (6543), sin prepared/statement cache.
TLS habilitado. NullPool en la app; el pool lo maneja PgBouncer.

Provee:
- engine (create_async_engine)
- SessionLocal (async_sessionmaker)
- Base (DeclarativeBase con naming convention para Alembic)
- Dependencias FastAPI: get_async_session / get_db
- context manager: session_scope()
- check_database_health()

Notas:
- Se añaden timeouts a nivel de conexión (asyncpg: timeout, command_timeout).
- Se aplica SET SESSION statement_timeout al abrir cada sesión (configurable).
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
# IMPORTANTE: Se recomienda truststore>=0.8 para API estable
try:
    import truststore  # type: ignore
except Exception:  # pragma: no cover
    truststore = None  # type: ignore

from sqlalchemy import MetaData, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.shared.config import settings

# Windows event loop policy (debe configurarse antes de crear el engine)
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

logger = logging.getLogger("uvicorn.error")

# Silenciar errores ruidosos de cierre de conexiones de NullPool (TimeoutError al cerrar asyncpg)
try:
    nullpool_logger = logging.getLogger("sqlalchemy.pool.impl.NullPool")
    # Solo registrará CRITICAL; los ERROR generados al cerrar conexiones no aparecerán
    nullpool_logger.setLevel(logging.CRITICAL)
except Exception:
    pass


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
            # Si falla, caemos a str() como último recurso
            return str(value)
    return str(value)


# ── Parámetros (valores desde settings) normalizados a str
DB_USER = _to_str_setting(getattr(settings, "db_user", None))
DB_PASSWORD = _to_str_setting(getattr(settings, "db_password", None))
DB_HOST = _to_str_setting(getattr(settings, "db_host", None))          # ej. aws-0-us-east-2.pooler.supabase.com
DB_PORT = _to_str_setting(getattr(settings, "db_port", None))          # 6543 (PgBouncer)
DB_NAME = _to_str_setting(getattr(settings, "db_name", None))

DB_ECHO_SQL = bool(getattr(settings, "db_echo_sql", False))
DB_TLS_ENABLED = bool(getattr(settings, "db_tls", True))  # TLS habilitado por defecto

# Timeouts configurables (segundos / milisegundos)
DB_CONNECT_TIMEOUT_S: float = float(getattr(settings, "db_connect_timeout_s", 5.0))
DB_COMMAND_TIMEOUT_S: float = float(getattr(settings, "db_command_timeout_s", 5.0))
DB_SESSION_STATEMENT_TIMEOUT_MS: int = int(getattr(settings, "db_session_statement_timeout_ms", 5000))

# DSN asyncpg para PgBouncer/Supabase (puerto 6543)
# URL-encode de credenciales para manejar caracteres especiales
ASYNC_DSN = (
    f"postgresql+asyncpg://"
    f"{quote_plus(DB_USER)}:"
    f"{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Log de conexión (debug en dev, info en prod)
log_level = logger.debug if DB_ECHO_SQL else logger.info
log_level(
    f"[DB] Conectando a PgBouncer → {DB_HOST}:{DB_PORT}/{DB_NAME} "
    f"(asyncpg, echo={DB_ECHO_SQL}, tls={DB_TLS_ENABLED})"
)

# ── SSLContext moderno (evita DeprecationWarning)
def build_ssl_context() -> ssl.SSLContext:
    """
    Crea un SSLContext para conexiones TLS a Postgres.

    Comportamiento:
      - En entornos de desarrollo (PYTHON_ENV in {local, development}), se usa
        un contexto sin verificación estricta de certificado, evitando problemas
        con truststore en Windows.
      - En otros entornos:
          * Si hay truststore, usa el almacén del sistema con protocolo explícito.
          * Si no, usa ssl.create_default_context con verificación estándar.
    """
    env = os.getenv("PYTHON_ENV", "").lower()
    is_dev = env in ("local", "development", "dev", "")

    if is_dev:
        # ⚠️ Solo para desarrollo local:
        #   - No verificar hostname
        #   - No requerir certificado válido
        #   - No usar truststore (evitamos errores con raíz no confiable en Windows)
        ctx = ssl._create_unverified_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # Entornos no-dev: verificación estricta
    if truststore is not None:
        # IMPORTANTE: indicar el protocolo para evitar DeprecationWarning
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # type: ignore[arg-type]
    else:
        ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# Construir ssl_context solo si TLS está habilitado
ssl_context = build_ssl_context() if DB_TLS_ENABLED else None

# ── Engine (sin pool app-side; PgBouncer se encarga del pooling)
# Genera nombres únicos para prepared statements (evita colisiones en PgBouncer transaction mode)
def _prepared_statement_name_func() -> str:
    return f"__asyncpg_{uuid4().hex[:8]}__"

# Construir connect_args dinámicamente según TLS
connect_args = {
    "statement_cache_size": 0,              # asyncpg
    "prepared_statement_cache_size": 0,     # asyncpg
    "prepared_statement_name_func": _prepared_statement_name_func,
    # search_path por si no quieres schema-qualified en cada query
    "server_settings": {"search_path": "public"},
    # Timeouts a nivel de conexión/consulta (asyncpg)
    "timeout": DB_CONNECT_TIMEOUT_S,        # timeout de conexión
    "command_timeout": DB_COMMAND_TIMEOUT_S # timeout por consulta en segundos
}

# Solo agregar SSL si está habilitado
if DB_TLS_ENABLED and ssl_context is not None:
    connect_args["ssl"] = ssl_context

engine = create_async_engine(
    ASYNC_DSN,
    poolclass=NullPool,
    pool_pre_ping=False,  # con NullPool y PgBouncer no aporta mucho; evitamos round-trip extra
    echo=DB_ECHO_SQL,
    execution_options={"prepared_statement_cache_size": 0},
    connect_args=connect_args,
)

# ── Session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)

# ── Hook de configuración por sesión
async def _configure_session(session: AsyncSession) -> None:
    """
    Aplica configuraciones por sesión:
    - SET SESSION statement_timeout para limitar consultas “largas” en esta sesión.
    """
    try:
        await session.execute(text(f"SET SESSION statement_timeout = {DB_SESSION_STATEMENT_TIMEOUT_MS}"))
    except Exception as e:
        # No es fatal si el backend no soporta el comando (p.ej. distinto a Postgres)
        logger.debug(f"[DB] No se pudo aplicar statement_timeout de sesión: {e}")

# ── Dependencias FastAPI
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        # Configuración de sesión (timeouts)
        await _configure_session(session)
        try:
            yield session
        except (OperationalError, SQLAlchemyError):
            # Importante: rollback para liberar cualquier transacción/lock
            try:
                await session.rollback()
            except Exception:
                pass
            raise
        finally:
            # El context manager cierra la sesión; aquí solo nos aseguramos de finalizar bien
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass

# Alias legacy para routers antiguos
async def get_db() -> AsyncGenerator[AsyncSession, None]:
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

# ── Context manager reutilizable en scripts/tests
@asynccontextmanager
async def session_scope(configure: bool = True) -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        if configure:
            await _configure_session(session)
        try:
            yield session
            # Dejo el commit/rollback a quien use el scope; esto es solo un helper
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            except Exception:
                pass

# ── Health check
async def check_database_health(timeout_s: float = 3.0, sql: str = "SELECT 1") -> bool:
    """
    Verifica conectividad a la base de datos.
    
    Args:
        timeout_s: Tiempo máximo de espera en segundos
        sql: Query SQL a ejecutar (default: "SELECT 1")
    
    Returns:
        True si la conexión es exitosa, False en caso contrario
    """
    try:
        async with asyncio.timeout(timeout_s):
            async with engine.connect() as conn:
                await conn.execute(text(sql))
        return True
    except Exception:
        return False

__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_async_session",
    "get_db",
    "session_scope",
    "check_database_health",
]
# Fin del archivo backend/app/shared/database/database.py
