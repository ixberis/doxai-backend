
# backend/tests/conftest.py
# -*- coding: utf-8 -*-
"""
Config global de tests para DoxAI.

Ajustado para soportar correctamente drivers asyncpg y psycopg:
- psycopg/libpq usa sslmode=require en la URL (no acepta `ssl` en connect_args)
- asyncpg usa ssl=require en la URL y sí acepta `ssl` (SSLContext) en connect_args

También:
- Pre-carga de modelos para resolver relationships('ClassName')
- Esquema SQLite "seguro" (excluye tablas con tipos exclusivos de Postgres como CITEXT/JSONB)
- Ruta de integración a PostgreSQL para pruebas del módulo payments
- (Nuevo) Forzar stubs del módulo Payments y cliente httpx con ciclo de vida
"""

import os
import sys
import pathlib
import warnings
import importlib
import asyncio
import ssl
import time
import re
from typing import Iterable, List, Dict, Set
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import pytest
import certifi
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from collections.abc import AsyncIterator 

from pathlib import Path
from dotenv import load_dotenv
import os

# ============================================================
# Cargar variables de entorno desde backend/.env para pytest
# ============================================================
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

assert os.getenv("DATABASE_URL"), "DATABASE_URL no cargada desde .env"
assert os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL no cargada desde .env"



# -----------------------------------------------------------------------------
# 0) Defaults útiles para la suite (evita sorpresas en pagos)
# -----------------------------------------------------------------------------
# Permite que los webhooks acepten payloads en pruebas sin firma estricta
os.environ.setdefault("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
# Evita llamadas reales a proveedores si algún servicio no está monkeypatcheado
os.environ.setdefault("PAYMENTS_TEST_MODE", "1")
# (Nuevo) Usa ruteadores STUBS de Payments en pruebas
os.environ.setdefault("USE_PAYMENT_STUBS", "true")
# (Nuevo) Permite http://localhost para success/cancel en checkout de pruebas
os.environ.setdefault("PAYMENTS_ALLOW_HTTP_LOCAL", "true")

# -----------------------------------------------------------------------------
# 0.b) App FastAPI y cliente httpx (httpx>=0.28, con ciclo de vida)
# -----------------------------------------------------------------------------
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

@pytest.fixture(scope="session")
def app():
    """
    Carga la aplicación principal de FastAPI **después** de setear env vars,
    garantizando que app/routes monte los STUBS cuando USE_PAYMENT_STUBS=true.
    """
    from app.main import app as fastapi_app
    return fastapi_app

@pytest.fixture
async def async_client(app) -> AsyncIterator[AsyncClient]:
    """
    Cliente HTTP asíncrono contra la app con ASGITransport (sin 'lifespan' param)
    y gestión de startup/shutdown mediante asgi-lifespan.
    """
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

# -----------------------------------------------------------------------------
# 1) Variables mínimas de entorno
# -----------------------------------------------------------------------------
os.environ.setdefault("SENTRY_DSN", "http://localhost")
os.environ.setdefault("SUPABASE_BUCKET_NAME", "test-bucket")
os.environ.setdefault("JWT_SECRET", "test-secret-for-auth-suite-please-change")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_MINUTES", "1440")
os.environ.setdefault("ACTIVATION_TOKEN_EXPIRE_MINUTES", "60")

# -----------------------------------------------------------------------------
# 2) Asegura .../backend en sys.path
# -----------------------------------------------------------------------------
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
assert (BACKEND_ROOT / "app").exists(), f"'app' no existe en {BACKEND_ROOT}"

SQL_ROOT = (BACKEND_ROOT.parent / "database").resolve()

# -----------------------------------------------------------------------------
# Utilidad: normalizar parámetros SSL según el driver
# -----------------------------------------------------------------------------
def _normalize_ssl_params(dsn: str) -> str:
    u = urlsplit(dsn)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    scheme = u.scheme.lower()
    if scheme.startswith("postgresql+psycopg"):
        # psycopg/libpq: nada de ?ssl=..., sólo sslmode=require
        q.pop("ssl", None)
        q["sslmode"] = "require"
    elif scheme.startswith("postgresql+asyncpg"):
        # asyncpg: usa ?ssl=require; quitar sslmode si estuviera
        q.pop("sslmode", None)
        q["ssl"] = "require"
    new_query = urlencode(q, doseq=True)
    return urlunsplit((u.scheme, u.netloc, u.path, new_query, u.fragment))

# -----------------------------------------------------------------------------
# Preload ORM Models (evita fallos por relaciones en string)
# -----------------------------------------------------------------------------
def _import_modules(paths: Iterable[str]) -> None:
    for p in paths:
        try:
            importlib.import_module(p)
        except Exception:
            # Intencional: no romper la recolección si algún módulo no compila aquí
            pass

@pytest.fixture(scope="session", autouse=True)
def preload_orm_models():
    """
    Importa modelos necesarios para que SQLAlchemy resuelva relationships('ClassName')
    sin obligar a crear sus tablas en SQLite (el esquema seguro filtra tipos PG-only).
    """
    _import_modules([
        # AUTH (necesarios para la suite de auth)
        "app.modules.auth.models.user_models",
        "app.modules.auth.models.activation_models",
        "app.modules.auth.models.password_reset_models",
        "app.modules.auth.models.login_models",

        # PROJECTS / FILES (para resolver referencias por nombre, p.ej. 'ProjectFile')
        "app.modules.projects.models.project_models",
        "app.modules.projects.models.project_file_models",
        "app.modules.files.models.input_file_models",
        "app.modules.files.models.input_file_metadata_models",
        "app.modules.files.models.product_file_models",
        "app.modules.files.models.product_file_metadata_models",
        "app.modules.files.models.product_file_activity_models",

        # ⚠️ NO importamos aquí models de PAYMENTS; sus tests de BD usan 'adb' (PG).
        # "app.modules.payments.models.payment_models",
        # "app.modules.payments.models.payment_event_models",
        # "app.modules.payments.models.refund_models",
        # "app.modules.payments.models.credit_transaction_models",
        # "app.modules.payments.models.usage_reservation_models",
        # "app.modules.payments.models.wallet_models",
    ])

# -----------------------------------------------------------------------------
# Esquema SQLite "seguro": excluye tablas con tipos de Postgres (CITEXT/JSONB)
# -----------------------------------------------------------------------------
from app.shared.database.database import Base  # Base global de los modelos

PG_ONLY_TYPE_NAMES = {"CITEXT", "JSONB"}
PG_ONLY_MODULE_SNIPPET = "sqlalchemy.dialects.postgresql"

# Tablas que NO deben crearse en SQLite, además de las que detectemos por tipo
EXPLICIT_SQLITE_EXCLUDE = {
    "projects",  # user_email::CITEXT
    # agrega aquí si aparece alguna otra
}

def _col_is_pg_only(col) -> bool:
    t = type(col.type)
    if t.__name__.upper() in PG_ONLY_TYPE_NAMES:
        return True
    if PG_ONLY_MODULE_SNIPPET in getattr(t, "__module__", ""):
        return True
    s = str(col.type).upper()
    return any(x in s for x in PG_ONLY_TYPE_NAMES)

def _names_pg_only_tables() -> set[str]:
    names = set()
    for t in Base.metadata.sorted_tables:
        if any(_col_is_pg_only(c) for c in t.columns):
            names.add(t.name)
    return names

def _fk_targets(table) -> set[str]:
    """
    Devuelve el conjunto de nombres de tablas a las que `table` hace referencia
    vía FK. Usamos `fk.target_fullname` como fallback cuando no está resuelto.
    """
    targets = set()
    for fk in table.foreign_keys:
        # si el mapper resolvió, está en fk.column.table.name
        col = getattr(fk, "column", None)
        if col is not None and getattr(col, "table", None) is not None:
            targets.add(col.table.name)
            continue
        # fallback: 'schema.table.col' o 'table.col'
        target = getattr(fk, "target_fullname", "") or ""
        if target:
            parts = target.split(".")
            if len(parts) >= 2:
                # ...schema.table.column  |  table.column
                targets.add(parts[-2])
    return targets

def _compute_sqlite_safe_tables() -> list:
    """
    1) Marca como excluidas: tablas con tipos PG-only + exclusiones explícitas.
    2) Propaga exclusión a cualquier tabla que tenga FKs hacia una excluida.
    3) Devuelve la lista final de tablas seguras (por nombre).
    """
    all_tables = list(Base.metadata.sorted_tables)
    excluded = set(EXPLICIT_SQLITE_EXCLUDE)
    excluded |= _names_pg_only_tables()

    name_to_table = {t.name: t for t in all_tables}

    # Propagación por dependencias (Fks → excluidas), hasta punto fijo
    changed = True
    while changed:
        changed = False
        for t in all_tables:
            if t.name in excluded:
                continue
            targets = _fk_targets(t)
            if any(trg in excluded for trg in targets):
                excluded.add(t.name)
                changed = True

    safe_tables = [name_to_table[n] for n in name_to_table.keys() if n not in excluded]
    return safe_tables

def create_sqlite_safe_schema(bind_engine) -> None:
    """
    Crea únicamente las tablas “seguras” en SQLite usando un MetaData temporal,
    evitando compilar tipos PG-only y evitando tablas que dependan de ellas.
    """
    safe_md = MetaData()
    for t in _compute_sqlite_safe_tables():
        # ⚠️ usar API no deprecada
        t.to_metadata(safe_md)
    safe_md.create_all(bind=bind_engine)

# -----------------------------------------------------------------------------
# Fixtures SQLite (unit tests ligeros: auth, utils, etc.)
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def engine():
    """Engine SQLite en memoria con creación de esquema 'seguro'."""
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    create_sqlite_safe_schema(eng)  # <- en vez de Base.metadata.create_all(bind=eng)
    try:
        yield eng
    finally:
        eng.dispose()

@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s
        s.rollback()

# -----------------------------------------------------------------------------
# Fixtures PostgreSQL async (integración, usado por payments)
# -----------------------------------------------------------------------------
def _pick_pg_url() -> str:
    raw = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not raw:
        return ""
    return _normalize_ssl_params(raw)

TEST_DATABASE_URL = _pick_pg_url()

SQL_FILES_ORDER: List[str] = [
    # 00_common
    "00_common/01_extensions_global.sql",
    "00_common/02_helpers.sql",
    "00_common/03_enums_email.sql",
    "00_common/04_rls_self_service.sql",
    "00_common/05_refresh_rotation.sql",
    "00_common/06_jobs.sql",
    # modules (using index files)
    "auth/_index_auth.sql",
    "payments/_index_payments.sql",
    "projects/_index_projects.sql",
    "files/_index_files.sql",
    "rag/_index_rag.sql",
]

def _read_sql(rel_path: str) -> str:
    abs_path = SQL_ROOT / rel_path
    if not abs_path.exists():
        raise FileNotFoundError(f"No existe el script SQL: {abs_path}")
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()

def _expand_psql_includes(content: str, base_path: str) -> str:
    """Expande comandos \ir (include relative) de psql recursivamente."""
    lines = content.split('\n')
    expanded = []
    
    for line in lines:
        stripped = line.strip()
        # Ignorar comandos \echo y otros meta-comandos de psql
        if stripped.startswith('\\echo') or stripped.startswith('\\set') or stripped.startswith('\\timing'):
            continue
        
        # Procesar comandos \ir (include relative)
        ir_match = re.match(r'\\ir\s+(.+)', stripped)
        if ir_match:
            include_file = ir_match.group(1).strip()
            # Construir path relativo desde el directorio del archivo actual
            base_dir = pathlib.Path(base_path).parent
            include_rel_path = str(base_dir / include_file)
            
            # Leer y expandir recursivamente el archivo incluido
            try:
                included_content = _read_sql(include_rel_path)
                expanded_included = _expand_psql_includes(included_content, include_rel_path)
                expanded.append(expanded_included)
            except FileNotFoundError:
                # Si el archivo no existe, lo ignoramos (puede ser opcional)
                continue
        else:
            expanded.append(line)
    
    return '\n'.join(expanded)

def _split_sql_statements(sql_text: str) -> List[str]:
    stmts, buf = [], []
    in_single = in_double = in_block_comment = in_dollar = False
    dollar_tag = ""
    i, n = 0, len(sql_text)

    def flush():
        s = "".join(buf).strip()
        if s:
            stmts.append(s)
        buf.clear()

    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ""
        if not in_single and not in_double and not in_dollar:
            if in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue
            else:
                if ch == "/" and nxt == "*":
                    in_block_comment = True
                    i += 2
                    continue
        if not in_single and not in_double and not in_dollar and ch == "-" and nxt == "-":
            while i < n and sql_text[i] != "\n":
                i += 1
            buf.append("\n")
            i += 1
            continue
        if not in_single and not in_double and not in_block_comment:
            if not in_dollar and ch == "$":
                j = i + 1
                while j < n and (sql_text[j].isalnum() or sql_text[j] == "_"):
                    j += 1
                if j < n and sql_text[j] == "$":
                    dollar_tag = sql_text[i:j + 1]
                    in_dollar = True
                    buf.append(dollar_tag)
                    i = j + 1
                    continue
            elif in_dollar:
                tag_len = len(dollar_tag)
                if tag_len > 0 and sql_text[i:i + tag_len] == dollar_tag:
                    buf.append(dollar_tag)
                    i += tag_len
                    in_dollar = False
                    continue
        if not in_dollar and not in_block_comment:
            if ch == "'" and not in_double:
                in_single = not in_single
                buf.append(ch)
                i += 1
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                buf.append(ch)
                i += 1
                continue
        if ch == ";" and not in_single and not in_double and not in_block_comment and not in_dollar:
            flush()
            i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return [s for s in stmts if s.strip()]

async def _run_sql_file(conn, rel_path: str) -> None:
    raw = _read_sql(rel_path)
    # Expandir comandos \ir recursivamente si es un archivo _index
    if '_index_' in rel_path or rel_path.endswith('_index.sql'):
        raw = _expand_psql_includes(raw, rel_path)
    
    for stmt in _split_sql_statements(raw):
        up = stmt.strip().upper()
        if up in ("BEGIN", "COMMIT"):
            continue
        await conn.exec_driver_sql(stmt)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

def _make_ssl_context(strict: bool = True) -> ssl.SSLContext:
    if strict:
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

@pytest.fixture(scope="session")
async def pg_engine():
    """
    Motor async PostgreSQL para tests de integración (payments).
    - psycopg/libpq: NO pasar `ssl` ni `prepared_statement_cache_size` en connect_args
    - asyncpg: sí pasar `ssl` (SSLContext) y `prepared_statement_cache_size`
    """
    url = _pick_pg_url()
    if not url:
        pytest.skip("Define TEST_DATABASE_URL o DATABASE_URL (con SSL válido).")

    scheme = urlsplit(url).scheme.lower()
    using_psycopg = scheme.startswith("postgresql+psycopg")
    using_asyncpg = scheme.startswith("postgresql+asyncpg")

    strict_ctx = _make_ssl_context(strict=True)
    insecure_ctx = _make_ssl_context(strict=False)
    insecure_ok = os.getenv("TESTS_SSL_INSECURE_OK", "0") == "1"

    def _connect_args(strict: bool):
        if using_asyncpg:
            # asyncpg SÍ acepta SSLContext y tuning del statement cache
            return {
                "ssl": strict_ctx if strict else insecure_ctx,
                "prepared_statement_cache_size": 0,
            }
        # psycopg: deshabilitar prepared statements cache para evitar colisiones
        return {
            "prepare_threshold": None,  # Deshabilita prepared statements en psycopg3
        }

    eng = create_async_engine(
        url,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=_connect_args(strict=True),
    )

    for attempt in range(3):
        try:
            async with eng.begin() as conn:
                for path in SQL_FILES_ORDER:
                    await _run_sql_file(conn, path)
            break
        except ssl.SSLCertVerificationError:
            if not insecure_ok:
                raise
            await eng.dispose()
            eng = create_async_engine(
                url,
                future=True,
                pool_pre_ping=True,
                poolclass=NullPool,
                connect_args=_connect_args(strict=False),
            )
            async with eng.begin() as conn:
                for path in SQL_FILES_ORDER:
                    await _run_sql_file(conn, path)
            break
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (2 ** attempt))

    yield eng
    await eng.dispose()

@pytest.fixture(scope="function")
async def adb(pg_engine):
    """Async DB session sobre PostgreSQL para pruebas de integración (payments)."""
    SessionLocal = async_sessionmaker(pg_engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        async with session.begin():
            yield session

# -----------------------------------------------------------------------------
# Stubs y services reales del módulo Auth (ajustados a tus archivos)
# -----------------------------------------------------------------------------
class StubEmailSender:
    async def send_activation_email(self, *, to: str, token: str) -> None:
        return None
    async def send_password_reset_email(self, *, to: str, token: str) -> None:
        return None
    async def send_welcome_email(self, *, to_email: str, full_name: str, credits_assigned: int) -> None:
        return None

class StubRecaptchaVerifier:
    def __init__(self, ok: bool = True):
        self.ok = ok
    async def verify(self, token: str) -> bool:
        return self.ok

@pytest.fixture(scope="function")
def email_sender():
    return StubEmailSender()

@pytest.fixture(scope="function")
def captcha_ok():
    return StubRecaptchaVerifier(ok=True)

@pytest.fixture(scope="function")
def captcha_bad():
    return StubRecaptchaVerifier(ok=False)

from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.auth_service import AuthService

# --- Emisor de tokens de prueba (stub) ---
class TestingTokenIssuer:
    def __init__(self) -> None:
        self.revoked: Set[str] = set()
        self.issued: Dict[str, str] = {}
    def create_access_token(self, *, sub: str) -> str:
        return f"access_{sub}_{int(time.time()*1000)}"
    async def issue_pair(self, *, user_id: int) -> dict:
        ts = int(time.time() * 1000)
        access = f"access_{user_id}_{ts}"
        refresh = f"refresh_{user_id}_{ts}"
        self.issued[refresh] = access
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}
    async def refresh(self, *, refresh_token: str) -> dict:
        if refresh_token in self.revoked or refresh_token not in self.issued:
            raise RuntimeError("Invalid or revoked refresh token")
        ts = int(time.time() * 1000)
        new_access = f"access_refreshed_{ts}"
        self.issued[refresh_token] = new_access
        return {"access_token": new_access, "refresh_token": refresh_token, "token_type": "bearer"}
    async def revoke(self, *, refresh_token: str) -> None:
        self.revoked.add(refresh_token)

@pytest.fixture(scope="function")
def testing_token_issuer():
    return TestingTokenIssuer()

@pytest.fixture(scope="function")
def services_factory(adb, email_sender, captcha_ok, testing_token_issuer):
    """
    Devuelve tu pila de servicios reales alineada a AuthService:
      - UserService(adb)
      - ActivationService(adb)
      - PasswordResetService (instanciado internamente por AuthService)
      - TokenIssuer (stub)
      - EmailSender (stub) y reCAPTCHA (stub)
    """
    def _make():
        auth = AuthService(
            db=adb,
            email_sender=email_sender,
            recaptcha_verifier=captcha_ok,
            token_issuer=testing_token_issuer,
        )
        user = auth.user_service
        act = auth.activation_service
        # reset = auth.password_reset_service
        return user, act, None, None, None, auth
    return _make

def pytest_addoption(parser):
    parser.addoption(
        "--runintegration",
        action="store_true",
        default=False,
        help="Run integration-level tests (sets PAYMENTS_RUN_INTEGRATION=1 early, before collection).",
    )

def pytest_configure(config):
    # Se ejecuta ANTES de la recolección de módulos de test.
    if config.getoption("--runintegration"):
        os.environ["PAYMENTS_RUN_INTEGRATION"] = "1"

# -----------------------------------------------------------------------------
# Override del usuario actual para ruteadores que lean current_user (Auth/Payments)
# -----------------------------------------------------------------------------
from typing import Any
from fastapi import Request

@pytest.fixture(autouse=True)
def _override_current_user_dependency(request):
    """
    Si existe una fixture 'app' en el alcance, intentamos overridear la
    dependencia de autenticación (get_current_user | get_current_active_user).
    Lee el user_id desde el header 'X-User-ID' (lo que ya usan los tests).
    """
    app = None
    try:
        app = request.getfixturevalue("app")  # p.ej. definido en tests de routes
    except Exception:
        return  # No hay app en este módulo → no hacemos override

    if app is None:
        return

    # Intentamos resolver cualquiera de las dependencias típicas.
    candidates = [
        "app.modules.auth.dependencies.get_current_user",
        "app.modules.auth.dependencies.get_current_active_user",
    ]
    dep = None
    for dotted in candidates:
        try:
            module_path, attr = dotted.rsplit(".", 1)
            mod = importlib.import_module(module_path)
            dep = getattr(mod, attr)
            break
        except Exception:
            continue

    if dep is None:
        # No hay dependencia estándar → nada que overridear.
        return

    async def _fake_current_user(req: Request) -> Dict[str, Any]:
        xuid = req.headers.get("X-User-ID")
        if not xuid:
            from fastapi import HTTPException, status as _st
            raise HTTPException(status_code=_st.HTTP_401_UNAUTHORIZED, detail="Missing X-User-ID")
        return {"user_id": int(xuid), "email": f"user{xuid}@test.local", "is_active": True}

    app.dependency_overrides[dep] = _fake_current_user

    # Limpieza al salir del test
    def _finalizer():
        app.dependency_overrides.pop(dep, None)
    request.addfinalizer(_finalizer)

# -----------------------------------------------------------------------------
# Soporte de dependencias para tests de ruteadores (Projects, etc.)
# -----------------------------------------------------------------------------
import types
from fastapi import FastAPI
from app.shared.database import database as _db_mod
from app.modules.auth import services as _auth_mod  # usado por fastapi_app_for_projects

@pytest.fixture(scope="session")
def fastapi_app_for_projects():
    """
    App FastAPI mínima para tests de ruteadores del módulo Projects.
    Inyecta dependencias falsas (get_db, get_current_user).
    """
    app = FastAPI()
    # Dependencias fijas para eliminar 403 en tests
    def _fake_db():
        class _Dummy:
            pass
        yield _Dummy()
    async def _fake_current_user():
        return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "test@example.com"}
    app.dependency_overrides[_db_mod.get_db] = _fake_db
    app.dependency_overrides[_auth_mod.get_current_user] = _fake_current_user
    return app

# -----------------------------------------------------------------------------
# Silenciar warnings SSL/Bcrypt ruidosos en tests
# -----------------------------------------------------------------------------
warnings.filterwarnings("ignore", message=r"ssl\.SSLContext\(\) without protocol argument is deprecated")
warnings.filterwarnings("ignore", message=r"ssl\.PROTOCOL_TLS is deprecated")

# Fin del archivo backend/tests/conftest.py
