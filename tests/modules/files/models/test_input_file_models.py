# backend\tests\files\models\test_input_file_models.py

# -*- coding: utf-8 -*-
import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.modules.files.enums import FileType, FileLanguage, InputFileClass, StorageBackend
from app.modules.files.models.input_file_models import InputFile

@pytest.mark.asyncio
async def test_create_input_file_minimal(db):
    obj = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=uuid4(),
        input_file_display_name="tdr.pdf",
        input_file_original_name="Términos de referencia.pdf",
        input_file_type=FileType.pdf,
        input_file_mime_type="application/pdf",
        input_file_size_bytes=12345,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_storage_path="proj/tdr.pdf",
        input_file_uploaded_at=datetime.now(timezone.utc),
        input_file_language=FileLanguage.es,
        input_file_class=InputFileClass.source,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    assert obj.input_file_display_name == "tdr.pdf"
    assert obj.input_file_size_bytes == 12345

@pytest.mark.asyncio
async def test_input_file_defaults(db):
    obj = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=uuid4(),
        input_file_display_name="doc.txt",
        input_file_type=FileType.txt,
        input_file_mime_type="text/plain",
        input_file_size_bytes=10,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_storage_path="proj/doc.txt",
        input_file_uploaded_at=datetime.now(timezone.utc),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    assert obj.input_file_language is None or obj.input_file_language in (FileLanguage.es, FileLanguage.en)
# Fin del archivo backend\tests\files\models\test_input_file_models.py