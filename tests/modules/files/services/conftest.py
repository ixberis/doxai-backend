# -*- coding: utf-8 -*-
"""
backend/tests/modules/files/services/conftest.py

Fixtures comunes para tests del módulo Files.

Autor: Ixchel Beristáin
Fecha: 15/11/2025
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone


@pytest.fixture
async def sample_user(db_session):
    """Crea un usuario de prueba."""
    from app.modules.auth.models.user_models import AppUser
    from sqlalchemy import text
    
    # Limpiar datos previos
    await db_session.execute(text("DELETE FROM app_users"))
    await db_session.commit()
    
    user = AppUser(
        user_full_name=f"Test User {uuid4().hex[:8]}",
        user_email=f"test.user.{uuid4().hex[:8]}@example.com",
        user_password_hash="hashed",
        user_is_activated=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_project(db_session, sample_user):
    """Crea un proyecto de prueba."""
    from sqlalchemy import text
    
    # Limpiar datos previos
    await db_session.execute(text("DELETE FROM projects"))
    await db_session.commit()
    
    project_id = uuid4()
    
    await db_session.execute(
        text("""
            INSERT INTO projects (
                id, user_id, user_email, created_by, project_name, project_slug, 
                project_description, project_state, project_status, project_created_at
            ) VALUES (
                :id, :user_id, :user_email, :created_by, :project_name, :project_slug,
                :project_description, :project_state, :project_status, :project_created_at
            )
        """),
        {
            "id": str(project_id),
            "user_id": sample_user.user_id,
            "user_email": sample_user.user_email,
            "created_by": sample_user.user_id,
            "project_name": f"Test Project {uuid4().hex[:6]}",
            "project_slug": f"test-project-{uuid4().hex[:8]}",
            "project_description": "Test project for integration tests",
            "project_state": "created",
            "project_status": "in_process",
            "project_created_at": datetime.now(timezone.utc),
        },
    )
    await db_session.commit()
    
    class Project:
        def __init__(self, project_id):
            self.project_id = project_id
    
    return Project(project_id)


@pytest.fixture
async def sample_input_file(db_session, sample_project, sample_user):
    """Crea un archivo insumo de prueba."""
    from app.modules.files.models.input_file_models import InputFile
    from app.modules.files.enums import FileLanguage, StorageBackend, FileType
    
    input_file = InputFile(
        input_file_id=uuid4(),
        project_id=sample_project.project_id,
        input_file_uploaded_by=sample_user.user_id,
        input_file_display_name="test_input.pdf",
        input_file_storage_path=f"test/input_{uuid4().hex[:8]}.pdf",
        input_file_size_bytes=1024,
        input_file_mime_type="application/pdf",
        input_file_type=FileType.pdf,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_language=FileLanguage.es,
        input_file_uploaded_at=datetime.now(timezone.utc),
    )
    db_session.add(input_file)
    await db_session.commit()
    await db_session.refresh(input_file)
    return input_file


@pytest.fixture
async def sample_product_file(db_session, sample_project, sample_user):
    """Crea un archivo producto de prueba."""
    from app.modules.files.models.product_file_models import ProductFile
    from app.modules.files.enums import ProductFileType, StorageBackend, ProductVersion
    
    product_file = ProductFile(
        product_file_id=uuid4(),
        project_id=sample_project.project_id,
        product_file_generated_by=sample_user.user_id,
        product_file_display_name="test_product.pdf",
        product_file_storage_path=f"test/product_{uuid4().hex[:8]}.pdf",
        product_file_size_bytes=2048,
        product_file_mime_type="application/pdf",
        product_file_type=ProductFileType.report,
        product_file_storage_backend=StorageBackend.supabase,
        product_file_version=ProductVersion.v1,
        product_file_generated_at=datetime.now(timezone.utc),
    )
    db_session.add(product_file)
    await db_session.commit()
    await db_session.refresh(product_file)
    return product_file


# Fin del archivo backend/tests/modules/files/services/conftest.py
