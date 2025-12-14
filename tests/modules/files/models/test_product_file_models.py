# backend\tests\files\models\test_product_file_models.py

# -*- coding: utf-8 -*-
import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.modules.files.enums import ProductFileType, ProductVersion, FileLanguage, StorageBackend
from app.modules.files.models.product_file_models import ProductFile

@pytest.mark.asyncio
async def test_create_product_file(db):
    obj = ProductFile(
        product_file_id=uuid4(),
        project_id=uuid4(),
        product_file_generated_by=uuid4(),
        product_file_display_name="matriz.xlsx",
        product_file_original_name="Matriz de Cumplimiento.xlsx",
        product_file_type=ProductFileType.report,  # Changed from compliance_matrix
        product_file_version=ProductVersion.v1,
        product_file_mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        product_file_size_bytes=4096,
        product_file_storage_backend=StorageBackend.supabase,
        product_file_storage_path="proj/matriz.xlsx",
        product_file_generated_at=datetime.now(timezone.utc),
        product_file_language=FileLanguage.es,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    assert obj.product_file_display_name.endswith(".xlsx")
    assert obj.product_file_version == ProductVersion.v1

# Fin del archivo backend\tests\files\models\test_product_file_models.py