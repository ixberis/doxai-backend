# backend\tests\files\enums\test_files_enums.py

# -*- coding: utf-8 -*-
import pytest

from app.modules.files.enums import (
    FileCategory, FileType, Language,
    InputFileClass, InputProcessingStatus,
    ProductFileType, ProductVersion, GenerationMethod,
    ProductFileEvent, StorageBackend, ChecksumAlgo, IngestSource
)

def test_file_category_members_and_values():
    # Asegura presencia y valores canónicos
    assert FileCategory.input_files.value in {"input", "input_files", "inputs"}
    assert FileCategory.product_files.value in {"product", "product_files", "outputs"}

@pytest.mark.parametrize("member", [
    FileType.pdf, FileType.docx, FileType.txt, FileType.pptx, FileType.xlsx
])
def test_file_type_basic_members(member):
    assert isinstance(member.value, str)
    assert member.name.islower()

@pytest.mark.parametrize("lang", [Language.es, Language.en])
def test_language_values_are_str(lang):
    assert isinstance(lang.value, str)

def test_input_processing_status_has_expected_states():
    expected = {"uploaded", "queued", "processing", "parsed", "vectorized", "failed"}
    got = {m.value for m in InputProcessingStatus}
    assert expected.issubset(got)

def test_product_version_default_v1():
    assert ProductVersion.v1.value in {"v1", "1"}

def test_generation_method_members():
    assert "rag" in {m.value for m in GenerationMethod}

def test_storage_backend_members():
    assert {"local", "s3", "gcs"}.issubset({m.value for m in StorageBackend})

def test_checksum_algo_members():
    assert {"sha256", "md5"}.issubset({m.value for m in ChecksumAlgo})

def test_ingest_source_members():
    assert {"web", "upload", "email", "integration"}.intersection({m.value for m in IngestSource})

# Fin del archivo backend\tests\files\enums\test_files_enums.py
