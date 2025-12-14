# backend/tests/modules/files/services/product_files/conftest.py
# -*- coding: utf-8 -*-
"""
Fixtures compartidas para tests del módulo product_files.

Provee:
- sample_user: Usuario de prueba
- sample_project: Proyecto con project_id válido
- sample_product_file: ProductFile con todas las FKs requeridas
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.enums import StorageBackend, ProductFileType, ProductVersion


@pytest.fixture
async def sample_user(db_session):
    """Crea un usuario de prueba usando el modelo real AppUser."""
    from app.modules.auth.models.user_models import AppUser
    from app.modules.auth.enums import UserRole, UserStatus
    
    # Email único por test para evitar UNIQUE constraint
    user_email = f"test.user.{uuid4().hex[:8]}@example.com"
    
    user = AppUser(
        user_full_name="Test User",
        user_email=user_email,
        user_password_hash="dummy_hash",
        user_role=UserRole.customer,
        user_status=UserStatus.active,
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
            INSERT INTO projects 
            (id, user_id, user_email, project_name, project_slug, project_description, 
             project_state, project_status, project_created_at, project_updated_at)
            VALUES (:pid, :uid, :email, :name, :slug, :desc, :state, :status, :created, :updated)
        """),
        {
            "pid": str(project_id),
            "uid": str(sample_user.user_id),
            "email": sample_user.user_email,
            "name": "Test Project",
            "slug": "test-project",
            "desc": "A test project",
            "state": "created",
            "status": "active",
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
    )
    await db_session.commit()
    
    class Project:
        pass
    project = Project()
    project.id = project_id
    project.project_id = project_id
    project.owner_id = sample_user.user_id
    return project


@pytest.fixture
async def sample_product_file(db_session, sample_project, sample_user):
    """Crea un ProductFile de prueba con todas las relaciones necesarias."""
    from uuid import UUID
    
    # Convertir user_id INT a UUID para la FK
    user_uuid = UUID(int=sample_user.user_id)
    
    product_file = ProductFile(
        product_file_id=uuid4(),
        project_id=sample_project.project_id,
        product_file_generated_by=user_uuid,
        product_file_display_name="output.pdf",
        product_file_original_name="Output Document.pdf",
        product_file_type=ProductFileType.document,
        product_file_mime_type="application/pdf",
        product_file_storage_path=f"projects/{sample_project.project_id}/outputs/output.pdf",
        product_file_size_bytes=2048,
        product_file_storage_backend=StorageBackend.supabase,
        product_file_version=ProductVersion.v1,
        product_file_is_active=True,
        product_file_is_archived=False,
    )
    db_session.add(product_file)
    await db_session.commit()
    await db_session.refresh(product_file)
    return product_file
