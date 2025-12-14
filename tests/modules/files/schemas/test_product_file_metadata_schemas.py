# backend\tests\files\schemas\test_product_file_metadata_schemas.py

# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from app.modules.files.enums import GenerationMethod
from app.modules.files.schemas.product_file_metadata_schemas import ProductFileMetadataBase, ProductFileMetadataResponse

def test_product_file_metadata_base_optional_fields_exist():
    m = ProductFileMetadataBase(
        product_file_hash_checksum="abc",
        checksum_algo="sha256",
        product_file_generation_method=GenerationMethod.rag,
        generation_params={"k": "v"},
        product_file_extracted_at=datetime.now(timezone.utc).isoformat(),
        product_file_ragmodel_version_used="v1",
    )
    assert m.checksum_algo == "sha256"
    assert isinstance(m.generation_params, dict)

def test_product_file_metadata_response_minimal():
    r = ProductFileMetadataResponse(
        product_file_metadata_id="00000000-0000-0000-0000-000000000000",
        product_file_id="00000000-0000-0000-0000-000000000001",
        product_file_hash_checksum="abc123",
        product_file_extracted_at=datetime.now(timezone.utc).isoformat(),
        product_file_ragmodel_version_used="v1",
        product_file_generation_method=GenerationMethod.rag,
    )
    assert str(r.product_file_id).endswith("1")
# Fin del archivo backend\tests\files\schemas\test_product_file_metadata_schemas.py