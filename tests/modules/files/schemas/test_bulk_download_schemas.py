# backend\tests\files\schemas\test_bulk_download_schemas.py

# -*- coding: utf-8 -*-
from app.modules.files.enums import FileType, FileCategory
from app.modules.files.schemas.bulk_download_schemas import (
    BulkDownloadRequest, BulkDownloadResponseItem
)

def test_bulk_download_request_parses_enums():
    req = BulkDownloadRequest(
        project_id="00000000-0000-0000-0000-000000000000",
        category=FileCategory.input_files if hasattr(FileCategory, "input_files") else FileCategory("input_files"),
        file_types=[FileType.pdf, FileType.docx],
    )
    assert req.category
    assert len(req.file_types) == 2

def test_bulk_download_response_item_model():
    item = BulkDownloadResponseItem(
        file_id="00000000-0000-0000-0000-000000000000",
        file_name="tdr.pdf",
        status="ok",
        reason=None
    )
    assert item.status == "ok"
# Fin del archivo backend\tests\files\schemas\test_bulk_download_schemas.py