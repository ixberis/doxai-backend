# backend\tests\files\schemas\test_product_file_schemas.py

# -*- coding: utf-8 -*-
from app.modules.files.enums import ProductFileType, ProductVersion, FileCategory, Language
from app.modules.files.schemas.product_file_schemas import ProductFileCreate, ProductFileResponse

def test_product_file_create_defaults_and_alias():
    c = ProductFileCreate(
        project_id="00000000-0000-0000-0000-000000000001",
        product_file_name="out.docx",
        product_file_type=ProductFileType.proposal,
        product_file_mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        product_file_size_bytes=99,
        product_file_storage_backend="local",
        product_file_storage_path="p/out.docx",
        product_file_version=ProductVersion.v1,
        product_file_language=Language.es,
        product_file_category=FileCategory.product_files if hasattr(FileCategory, "product_files") else FileCategory("product_files"),
    )
    assert c.product_file_version == ProductVersion.v1
    assert c.product_file_size_bytes == 99

def test_product_file_response_alias_size():
    r = ProductFileResponse(
        product_file_id="00000000-0000-0000-0000-000000000000",
        project_id="00000000-0000-0000-0000-000000000001",
        product_file_name="out.pdf",
        product_file_type=ProductFileType.report,
        product_file_mime_type="application/pdf",
        product_file_size=100,  # alias -> _size_bytes
        product_file_storage_backend="local",
        product_file_storage_path="p/out.pdf",
        product_file_version=ProductVersion.v1,
        product_file_generated_at="2025-10-26T11:00:00Z",
        product_file_language=Language.es,
        product_file_category=FileCategory.product_files if hasattr(FileCategory, "product_files") else FileCategory("product_files"),
    )
    assert r.product_file_size_bytes == 100
# Fin del archivo backend\tests\files\schemas\test_product_file_schemas.py