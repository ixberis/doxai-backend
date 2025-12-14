# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/diagnostics/test_diagnostics_sql_smoke.py

Smoke tests para diagnósticos SQL de RAG - FASE 4.

Estos tests verifican que las vistas y funciones de diagnóstico SQL
se pueden ejecutar sin errores en el esquema actual.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 4)
"""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.diagnostics_sql
async def test_diagnostics_rag_integrity_runs(adb):
    """Test: Vista de integridad RAG se puede consultar sin error."""
    
    # Esta consulta debe ejecutarse sin lanzar excepción
    # (puede devolver 0 filas, lo cual es OK)
    query = text("""
        SELECT j.job_id
        FROM rag_jobs j
        LEFT JOIN rag_job_events e ON e.job_id = j.job_id
        GROUP BY j.job_id
        HAVING COUNT(e.job_event_id) = 0
        LIMIT 5
    """)
    
    result = await adb.execute(query)
    rows = result.fetchall()
    
    # No importa cuántas filas, sólo que no lance error
    assert rows is not None


@pytest.mark.asyncio
@pytest.mark.diagnostics_sql
async def test_diagnostics_embeddings_coverage_runs(adb):
    """Test: Vista de cobertura de embeddings se puede consultar sin error."""
    
    query = text("""
        SELECT
            c.file_id,
            e.embedding_model,
            COUNT(DISTINCT c.chunk_id) AS chunks,
            COUNT(DISTINCT e.embedding_id) FILTER (WHERE e.is_active) AS embeddings_activos
        FROM chunk_metadata c
        LEFT JOIN document_embeddings e
            ON e.file_id = c.file_id AND e.chunk_index = c.chunk_index
        GROUP BY 1, 2
        LIMIT 5
    """)
    
    result = await adb.execute(query)
    rows = result.fetchall()
    
    assert rows is not None


@pytest.mark.asyncio
@pytest.mark.diagnostics_sql
async def test_diagnostics_chunks_without_embeddings_runs(adb):
    """Test: Diagnóstico de chunks sin embeddings se puede ejecutar."""
    
    query = text("""
        SELECT c.file_id, COUNT(*) AS chunks, 
               COALESCE(
                   (SELECT COUNT(*) 
                    FROM document_embeddings e 
                    WHERE e.file_id = c.file_id 
                      AND e.is_active), 
                   0
               ) AS embeddings_activos
        FROM chunk_metadata c
        GROUP BY c.file_id
        HAVING COALESCE(
                   (SELECT COUNT(*) 
                    FROM document_embeddings e 
                    WHERE e.file_id = c.file_id 
                      AND e.is_active), 
                   0
               ) < COUNT(*)
        LIMIT 5
    """)
    
    result = await adb.execute(query)
    rows = result.fetchall()
    
    assert rows is not None


@pytest.mark.asyncio
@pytest.mark.diagnostics_sql
async def test_diagnostics_throttling_hotspots_runs(adb):
    """Test: Diagnóstico de throttling OCR se puede ejecutar."""
    
    # Esta tabla puede no existir en entorno de tests, permitimos error gracefully
    try:
        query = text("""
            SELECT
                provider,
                date_trunc('hour', window_start) AS hour_bucket,
                COUNT(*) AS events,
                SUM(cooldown_ms) AS cooldown_ms_sum
            FROM ocr_ratelimits
            GROUP BY 1, 2
            ORDER BY 2 DESC, 3 DESC
            LIMIT 5
        """)
        
        result = await adb.execute(query)
        rows = result.fetchall()
        
        assert rows is not None
    except Exception as e:
        # Si la tabla no existe en tests, OK (es una tabla de producción)
        assert "does not exist" in str(e).lower() or "no such table" in str(e).lower()


# Fin del archivo backend/tests/modules/rag/diagnostics/test_diagnostics_sql_smoke.py
