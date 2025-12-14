# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/conftest.py

Configuración de tests para el módulo Projects.
Usa PostgreSQL porque los modelos requieren CITEXT, JSONB y pg_enum.

Autor: Ixchel Beristain
Fecha: 2025-11-08
"""
import pytest
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

from app.shared.database import Base
from app.main import app as fastapi_app


def _get_sync_pg_url() -> str:
    """Convierte la URL async de PostgreSQL a versión sync y ajusta SSL para localhost."""
    raw = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not raw:
        return ""
    
    # Convertir postgresql+asyncpg:// a postgresql+psycopg://
    url = raw
    if "postgresql+asyncpg://" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    
    # Si es localhost, agregar sslmode=disable para evitar errores SSL
    if "localhost" in url or "127.0.0.1" in url:
        if "?" in url:
            url += "&sslmode=disable"
        else:
            url += "?sslmode=disable"
    
    return url


@pytest.fixture(scope="session")
def pg_sync_engine():
    """
    Engine sync PostgreSQL para tests del módulo Projects.
    Reutiliza la URL de TEST_DATABASE_URL.
    """
    url = _get_sync_pg_url()
    if not url:
        pytest.skip("Define TEST_DATABASE_URL o DATABASE_URL para tests de Projects")
    
    eng = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    
    # Crear esquema completo (las migraciones ya ejecutaron en pg_engine)
    # Solo verificamos que las tablas existen
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"No se pudo conectar a PostgreSQL: {e}")
    
    yield eng
    eng.dispose()


@pytest.fixture
def db(pg_sync_engine):
    """
    Session sync de PostgreSQL para tests del módulo Projects.
    """
    SessionLocal = sessionmaker(bind=pg_sync_engine, future=True)
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def client(pg_sync_engine):
    """
    TestClient sincrónico para probar endpoints del módulo Projects.
    Hace override de get_db y get_current_user.
    """
    from app.shared.database import database as db_module
    from app.modules.auth import services as auth_module
    
    def _override_get_db():
        SessionLocal = sessionmaker(bind=pg_sync_engine, future=True)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    async def _override_get_current_user():
        # Usuario fijo para tests
        return {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "test@example.com"
        }
    
    # Override de dependencias
    fastapi_app.dependency_overrides[db_module.get_db] = _override_get_db
    fastapi_app.dependency_overrides[auth_module.get_current_user] = _override_get_current_user
    
    client_instance = TestClient(fastapi_app)
    yield client_instance
    
    # Limpiar overrides después del test
    fastapi_app.dependency_overrides.clear()
