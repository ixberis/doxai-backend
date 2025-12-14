# backend/tests/modules/files/conftest.py
# -*- coding: utf-8 -*-
"""
Conftest compartido para todos los tests del módulo Files.

Ajustes clave:
- Motor ASYNC: sqlite+aiosqlite (memoria) para permitir tests @pytest.mark.asyncio.
- Fixture principal: db_session (AsyncSession). Se ofrece alias db para compatibilidad.
- Parcheo de tipos PostgreSQL (CITEXT/JSONB) a equivalentes SQLite.
- Registro de función char_length en SQLite (compat con Postgres).
- Creación ordenada de tablas de Files y Projects, ignorando schemas.
- Stubs mínimos para tablas 'app_users' y 'projects' si las FKs lo requieren.
- Mock de AsyncStorageClient para tests.
"""

import asyncio
import pytest
from typing import Dict
from sqlalchemy import event, text, Table, Column, String, JSON, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateTable, DropTable
from sqlalchemy.sql.schema import MetaData

# --- Import Base unificado (TODOS los modelos usan la misma instancia) ---
from app.shared.database.database import Base

# CRÍTICO: Importar TODOS los modelos ANTES de cualquier otra cosa
# para forzar su registro en Base.metadata.tables
from app.modules.auth.models import AppUser
from app.modules.projects.models import Project
from app.modules.files.models import (
    InputFile,
    ProductFile, 
    ProductFileActivity,
    InputFileMetadata,
    ProductFileMetadata,
)

# Tipos específicos de Postgres a normalizar
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy import Enum as SQLEnum


def _patch_pg_types_for_sqlite(metadata):
    """Reemplaza tipos Postgres (CITEXT/JSONB/Enum) por equivalentes compatibles con SQLite."""
    for table in metadata.tables.values():
        for col in table.columns:
            t = col.type
            if isinstance(t, CITEXT):
                col.type = String(collation="NOCASE")
            elif isinstance(t, JSONB):
                col.type = JSON()
            elif isinstance(t, SQLEnum):
                # Convertir enums de Postgres a String para SQLite
                col.type = String(50)


def _strip_schema(metadata):
    """Quita schema='public' (u otros) para compatibilidad con SQLite."""
    for tbl in metadata.tables.values():
        tbl.schema = None




@pytest.fixture(scope="session")
def anyio_backend():
    """Permite a pytest-anyio usar asyncio en el scope de sesión."""
    return "asyncio"


@pytest.fixture(scope="session")
async def engine():
    """
    Motor ASYNC SQLite en memoria.
    - Registra función char_length (equivalente a length en SQLite).
    - Parchea tipos Postgres a SQLite.
    - Crea tablas de todos los Base.* en orden, ignorando schema.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(eng.sync_engine, "connect")
    def _register_sqlite_functions(dbapi_conn, connection_record):
        # char_length(x) => len(x) o 0 si None
        dbapi_conn.create_function("char_length", 1, lambda x: len(x) if x else 0)

    # Crear TODAS las tablas desde la metadata ÚNICA compartida por todos los modelos
    async with eng.begin() as conn:
        def _create_all(sync_conn):
            # Verificar que los modelos se registraron
            print(f"[CONFTEST] Tablas registradas: {list(Base.metadata.tables.keys())}")
            
            # TODOS los modelos usan Base.metadata (una sola instancia compartida)
            _patch_pg_types_for_sqlite(Base.metadata)
            _strip_schema(Base.metadata)
            Base.metadata.create_all(bind=sync_conn)
        await conn.run_sync(_create_all)

    try:
        yield eng
    finally:
        # Teardown: drop todas las tablas desde la metadata única
        async with eng.begin() as conn:
            def _drop_all(sync_conn):
                Base.metadata.drop_all(bind=sync_conn)
            await conn.run_sync(_drop_all)

        await eng.dispose()


@pytest.fixture
async def db_session(engine):
    """
    Sesión ASYNC de base de datos con limpieza de metadatos de ProductFile
    antes de cada test y rollback automático al finalizar.
    """
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        # Limpieza explícita de ProductFileMetadata para evitar datos residuales entre tests
        try:
            await session.execute(delete(ProductFileMetadata))
            await session.flush()
        except Exception:
            # No queremos que un fallo de limpieza bloquee el inicio del test
            await session.rollback()
        try:
            yield session
        finally:
            # Asegura rollback de transacciones pendientes
            try:
                await session.rollback()
            except Exception:
                pass


@pytest.fixture
async def db(db_session):
    """
    Alias de compatibilidad: algunos tests podrían esperar 'db'.
    Entregamos la misma AsyncSession que db_session.
    """
    yield db_session


# --- Mock de AsyncStorageClient para tests ---
class MockStorageClient:
    """
    Mock compatible con AsyncStorageClient protocol para tests del módulo Files.
    """
    def __init__(self):
        self.uploads: Dict[tuple, tuple] = {}
        self.deleted: list = []

    async def upload_bytes(self, bucket: str, key: str, data: bytes, mime_type: str | None = None) -> None:
        """Simula subir bytes al storage."""
        self.uploads[(bucket, key)] = (data, mime_type)

    async def get_download_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        """Devuelve URL fake de descarga."""
        return f"https://mockstorage/{bucket}/{key}?expires_in={expires_in_seconds}"

    async def delete_object(self, bucket: str, key: str) -> None:
        """Simula eliminar objeto del storage."""
        self.deleted.append((bucket, key))


@pytest.fixture
def mock_storage() -> MockStorageClient:
    """Fixture que proporciona un mock de AsyncStorageClient."""
    return MockStorageClient()


# Fin del archivo

