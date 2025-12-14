# backend\tests\files\schemas\test_input_file_metadata_schemas.py

# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from app.modules.files.enums import InputProcessingStatus
from app.modules.files.schemas.input_file_metadata_schemas import (
    InputFileMetadataCreate, InputFileMetadataResponse
)

def test_input_file_metadata_create_basic():
    m = InputFileMetadataCreate(
        input_file_id="00000000-0000-0000-0000-000000000000",
        input_file_extracted_at=datetime.now(timezone.utc).isoformat(),
        input_file_hash_checksum="abc",
        input_file_parser_version="1.0.0",
        input_file_processing_status=InputProcessingStatus.parsed,
    )
    assert m.input_file_parser_version.startswith("1.")

def test_input_file_metadata_response_optional_fields():
    r = InputFileMetadataResponse(
        input_file_metadata_id="00000000-0000-0000-0000-000000000000",
        input_file_id="00000000-0000-0000-0000-000000000000",
        input_file_extracted_at=datetime.now(timezone.utc).isoformat(),
        input_file_hash_checksum=None,
        input_file_parser_version="1.0.0",
        input_file_processing_status=InputProcessingStatus.parsed,
    )
    assert r.input_file_hash_checksum is None
# Fin del archivo backend\tests\files\schemas\test_input_file_metadata_schemas.py