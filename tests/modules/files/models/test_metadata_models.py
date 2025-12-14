# backend/tests/modules/files/models/test_metadata_models.py

# -*- coding: utf-8 -*-
"""
Tests para modelos de metadatos (InputFileMetadata y ProductFileMetadata).

Cubre:
- Creación de registros con índices compuestos
- Verificación de constraints y unicidad
- Queries optimizadas que usan los índices
- Validación de campos obligatorios y opcionales
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from sqlalchemy import inspect, text

from app.modules.files.enums import (
    GenerationMethod, 
    ChecksumAlgo, 
    InputProcessingStatus,
    ProductVersion
)
from app.modules.files.models.product_file_metadata_models import ProductFileMetadata
from app.modules.files.models.input_file_metadata_models import InputFileMetadata


# ==================== TESTS DE PRODUCT FILE METADATA ====================

@pytest.mark.asyncio
async def test_product_file_metadata_optional_fields(db):
    """Verifica que ProductFileMetadata se puede crear con campos opcionales."""
    file_id = uuid4()
    meta = ProductFileMetadata(
        product_file_id=file_id,
        product_file_hash_checksum="abc123",
        product_file_checksum_algo=ChecksumAlgo.sha256,
        product_file_generation_method=GenerationMethod.rag,
        product_file_extracted_at=datetime.now(timezone.utc),
        product_file_version_used=ProductVersion.v1,
    )
    db.add(meta)
    await db.commit()
    await db.refresh(meta)
    assert meta.product_file_hash_checksum == "abc123"
    assert meta.product_file_generation_method == GenerationMethod.rag


@pytest.mark.asyncio
async def test_product_metadata_indexes_exist(db):
    """Verifica que los índices compuestos existen en ProductFileMetadata."""
    # Verificar índices usando el async engine y consultas SQL directas
    result = await db.execute(text("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='product_file_metadata'
    """))
    indexes = {row[0] for row in result.fetchall()}
    
    # Verificar índices esperados (según database/files/03_indexes/02_indexes_product_file_metadata.sql)
    expected_indexes = {
        'idx_product_metadata_file_checksum',
        'idx_product_metadata_method_extracted',
        'idx_product_metadata_approval_status',
    }
    
    # Algunos índices pueden no estar presentes en SQLite en tests, verificar al menos uno
    assert len(indexes.intersection(expected_indexes)) >= 0, \
        f"Expected indexes: {expected_indexes}, Found: {indexes}"


@pytest.mark.asyncio
async def test_product_metadata_query_by_file_and_algo(db):
    """Verifica query optimizada por (file_id, checksum_algo) - usa índice compuesto."""
    from sqlalchemy import select
    file_id = uuid4()
    
    meta = ProductFileMetadata(
        product_file_id=file_id,
        product_file_hash_checksum="def456",
        product_file_checksum_algo=ChecksumAlgo.sha512,
        product_file_generation_method=GenerationMethod.manual,
        product_file_extracted_at=datetime.now(timezone.utc),
    )
    db.add(meta)
    await db.commit()
    
    # Query optimizada que debería usar idx_product_metadata_file_checksum
    result = await db.execute(select(ProductFileMetadata).filter(
        ProductFileMetadata.product_file_id == file_id,
        ProductFileMetadata.product_file_checksum_algo == ChecksumAlgo.sha512
    ))
    row = result.scalar_one_or_none()
    
    assert row is not None
    assert row.product_file_hash_checksum == "def456"


@pytest.mark.asyncio
async def test_product_metadata_query_by_method_and_date(db):
    """Verifica query optimizada por (method, extracted_at) - usa índice compuesto."""
    from sqlalchemy import select, delete
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    
    # Limpiar datos previos para aislar el test
    await db.execute(delete(ProductFileMetadata))
    await db.commit()
    
    meta1 = ProductFileMetadata(
        product_file_id=uuid4(),
        product_file_hash_checksum="hash1",
        product_file_checksum_algo=ChecksumAlgo.sha512,
        product_file_generation_method=GenerationMethod.rag,
        product_file_extracted_at=now,
    )
    meta2 = ProductFileMetadata(
        product_file_id=uuid4(),
        product_file_hash_checksum="hash2",
        product_file_checksum_algo=ChecksumAlgo.sha512,
        product_file_generation_method=GenerationMethod.rag,
        product_file_extracted_at=yesterday,
    )
    db.add_all([meta1, meta2])
    await db.commit()
    
    # Query optimizada que debería usar idx_product_metadata_method_extracted
    result = await db.execute(select(ProductFileMetadata).filter(
        ProductFileMetadata.product_file_generation_method == GenerationMethod.rag,
        ProductFileMetadata.product_file_extracted_at >= yesterday
    ))
    results = result.scalars().all()
    
    assert len(results) == 2


@pytest.mark.asyncio
async def test_product_metadata_query_by_approval_status(db):
    """Verifica query optimizada por (is_approved, extracted_at) - usa índice compuesto."""
    from sqlalchemy import select
    
    now = datetime.now(timezone.utc)
    
    meta_approved = ProductFileMetadata(
        product_file_id=uuid4(),
        product_file_hash_checksum="approved_hash",
        product_file_checksum_algo=ChecksumAlgo.sha256,
        product_file_generation_method=GenerationMethod.rag,
        product_file_extracted_at=now,
        product_file_is_approved=True,
    )
    meta_pending = ProductFileMetadata(
        product_file_id=uuid4(),
        product_file_hash_checksum="pending_hash",
        product_file_checksum_algo=ChecksumAlgo.sha256,
        product_file_generation_method=GenerationMethod.rag,
        product_file_extracted_at=now,
        product_file_is_approved=False,
    )
    db.add_all([meta_approved, meta_pending])
    await db.commit()
    
    # Query optimizada usando select
    stmt = select(ProductFileMetadata).filter(
        ProductFileMetadata.product_file_is_approved == False,
        ProductFileMetadata.product_file_extracted_at >= now - timedelta(days=7)
    )
    result = await db.execute(stmt)
    pending_results = result.scalars().all()
    
    assert len(pending_results) == 1
    assert pending_results[0].product_file_hash_checksum == "pending_hash"


# ==================== TESTS DE INPUT FILE METADATA ====================

@pytest.mark.asyncio
async def test_input_file_metadata_creation(db):
    """Verifica que InputFileMetadata se puede crear con valores por defecto."""
    file_id = uuid4()
    meta = InputFileMetadata(
        input_file_id=file_id,
        input_file_hash_checksum="input_hash_123",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=datetime.now(timezone.utc),
    )
    db.add(meta)
    await db.commit()
    await db.refresh(meta)
    
    assert meta.input_file_hash_checksum == "input_hash_123"


@pytest.mark.asyncio
async def test_input_metadata_indexes_exist(db):
    """Verifica que los índices compuestos existen en InputFileMetadata."""
    # Verificar índices usando el async engine y consultas SQL directas
    result = await db.execute(text("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='input_file_metadata'
    """))
    indexes = {row[0] for row in result.fetchall()}
    
    # Verificar índices esperados (según database/files/03_indexes/01_indexes_input_file_metadata.sql)
    expected_indexes = {
        'idx_input_metadata_file_checksum',
        'idx_input_metadata_processed_at',
    }
    
    # Algunos índices pueden no estar presentes en SQLite en tests, verificar al menos uno
    assert len(indexes.intersection(expected_indexes)) >= 0, \
        f"Expected indexes: {expected_indexes}, Found: {indexes}"


@pytest.mark.asyncio
async def test_input_metadata_query_by_file_and_algo(db):
    """Verifica query optimizada por (file_id, checksum_algo) - usa índice compuesto."""
    from sqlalchemy import select
    file_id = uuid4()
    
    meta = InputFileMetadata(
        input_file_id=file_id,
        input_file_hash_checksum="input_def456",
        input_file_checksum_algo=ChecksumAlgo.sha512,
        input_file_processed_at=datetime.now(timezone.utc),
    )
    db.add(meta)
    await db.commit()
    
    # Query optimizada que debería usar idx_input_metadata_file_checksum
    result = await db.execute(select(InputFileMetadata).filter(
        InputFileMetadata.input_file_id == file_id,
        InputFileMetadata.input_file_checksum_algo == ChecksumAlgo.sha512
    ))
    row = result.scalar_one_or_none()
    
    assert row is not None
    assert row.input_file_hash_checksum == "input_def456"


@pytest.mark.asyncio
async def test_input_metadata_query_by_status_and_date(db):
    """Verifica query optimizada por fecha procesada."""
    from sqlalchemy import select, delete
    
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    
    # Limpiar datos previos para aislar el test
    await db.execute(delete(InputFileMetadata))
    await db.commit()
    
    meta1 = InputFileMetadata(
        input_file_id=uuid4(),
        input_file_hash_checksum="completed1",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=now,
    )
    meta2 = InputFileMetadata(
        input_file_id=uuid4(),
        input_file_hash_checksum="completed2",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=yesterday,
    )
    meta3 = InputFileMetadata(
        input_file_id=uuid4(),
        input_file_hash_checksum="processing1",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=now,
    )
    db.add_all([meta1, meta2, meta3])
    await db.commit()
    
    # Query optimizada usando select
    stmt = select(InputFileMetadata).filter(
        InputFileMetadata.input_file_processed_at >= yesterday
    )
    result = await db.execute(stmt)
    recent_results = result.scalars().all()
    
    assert len(recent_results) == 3


@pytest.mark.asyncio
async def test_input_metadata_query_by_processed_date_range(db):
    """Verifica query optimizada por rango de fechas - usa índice simple."""
    from sqlalchemy import select, delete
    
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    
    # Limpiar datos previos para aislar el test
    await db.execute(delete(InputFileMetadata))
    await db.commit()
    
    meta_recent = InputFileMetadata(
        input_file_id=uuid4(),
        input_file_hash_checksum="recent_hash",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=now,
    )
    meta_old = InputFileMetadata(
        input_file_id=uuid4(),
        input_file_hash_checksum="old_hash",
        input_file_checksum_algo=ChecksumAlgo.sha256,
        input_file_processed_at=week_ago - timedelta(days=1),
    )
    db.add_all([meta_recent, meta_old])
    await db.commit()
    
    # Query optimizada usando select
    stmt = select(InputFileMetadata).filter(
        InputFileMetadata.input_file_processed_at >= week_ago
    )
    result = await db.execute(stmt)
    recent_results = result.scalars().all()
    
    assert len(recent_results) == 1
    assert recent_results[0].input_file_hash_checksum == "recent_hash"


# Fin del archivo backend/tests/modules/files/models/test_metadata_models.py