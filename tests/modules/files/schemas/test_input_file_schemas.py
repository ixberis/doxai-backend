# backend\tests\files\schemas\test_input_file_schemas.py

# -*- coding: utf-8 -*-
from app.modules.files.enums import FileType, Language, InputProcessingStatus, InputFileClass, FileCategory
from app.modules.files.schemas.input_file_schemas import InputFileResponse, InputFileCreate

def test_input_file_response_alias_size_bytes():
    model = InputFileResponse(
        input_file_id="00000000-0000-0000-0000-000000000000",
        project_id="00000000-0000-0000-0000-000000000001",
        user_email="test@example.com",
        input_file_name="t.txt",
        input_file_original_name="t.txt",
        input_file_type=FileType.txt,
        input_file_mime_type="text/plain",
        input_file_size=42,  # alias -> _bytes
        input_file_storage_path="p/t.txt",
        input_file_uploaded_by="00000000-0000-0000-0000-000000000002",
        input_file_uploaded_at="2025-10-25T10:00:00Z",
        input_file_language=Language.es,
        input_file_class=InputFileClass.source,
        input_file_category=FileCategory.input_files if hasattr(FileCategory, "input_files") else FileCategory("input_files"),
        input_file_processing_status=InputProcessingStatus.parsed,
        input_file_is_active=True,
        input_file_is_archived=False,
    )
    assert model.input_file_size_bytes == 42

def test_input_file_create_minimal():
    c = InputFileCreate(
        file_name="a.pdf",
        file_type=FileType.pdf,
        mime_type="application/pdf",
        size_bytes=10,
        storage_backend="local",
        storage_path="p/a.pdf",
    )
    assert c.file_name == "a.pdf"
# Fin del archivo backend\tests\files\schemas\test_input_file_schemas.py