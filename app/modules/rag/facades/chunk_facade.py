# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/facades/chunk_facade.py

Facade para fase 'chunk': segmentación semántica y persistencia.
Divide texto en chunks y persiste en ChunkMetadata.

Responsabilidades:
- Segmentar texto según parámetros (max_tokens, overlap, reglas)
- Persistir chunks en ChunkMetadata con índices y metadatos
- Validar constraints (token_count >= 0, páginas válidas)
- Idempotencia por (file_id, params_hash)

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 3 - Implementación completa)
"""

from dataclasses import dataclass
from uuid import UUID
import re
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.chunk_models import ChunkMetadata
from app.modules.rag.repositories.chunk_metadata_repository import chunk_metadata_repository
from app.modules.rag.repositories.rag_job_event_repository import rag_job_event_repository
from app.modules.rag.enums import RagPhase
from app.modules.files.services.storage_ops_service import AsyncStorageClient

logger = logging.getLogger(__name__)


@dataclass
class ChunkParams:
    """Parámetros de chunking semántico."""
    max_tokens: int = 400
    overlap: int = 60
    # Futuros: semantic_rules, min_chunk_size, etc.


@dataclass
class ChunkingResult:
    """Resultado de operación de chunking."""
    total_chunks: int
    chunk_ids: list[UUID]


def _simple_tokenize(text: str) -> list[str]:
    """Tokenización simple por whitespace para estimación."""
    return re.findall(r'\S+', text)


def _split_text_into_chunks(
    text: str, 
    max_tokens: int = 400, 
    overlap: int = 60
) -> list[tuple[str, int]]:
    """
    Divide texto en chunks con overlap.
    
    Returns:
        Lista de tuplas (chunk_text, token_count)
    """
    tokens = _simple_tokenize(text)
    chunks = []
    
    i = 0
    while i < len(tokens):
        # Tomar max_tokens tokens
        chunk_tokens = tokens[i:i + max_tokens]
        chunk_text = ' '.join(chunk_tokens)
        chunks.append((chunk_text, len(chunk_tokens)))
        
        # Avanzar con overlap
        i += max(1, max_tokens - overlap)
    
    return chunks if chunks else [("", 0)]


async def chunk_text(
    db: AsyncSession,
    job_id: UUID,
    file_id: UUID,
    text_uri: str,
    params: ChunkParams,
    *,
    storage_client: AsyncStorageClient | None = None,
) -> ChunkingResult:
    """
    Segmenta texto y persiste chunks en ChunkMetadata.
    
    Args:
        db: Sesión de base de datos
        job_id: ID del job de indexación
        file_id: ID del archivo fuente
        text_uri: URI del texto a segmentar (formato: bucket/path)
        params: Parámetros de chunking
        storage_client: Cliente de almacenamiento (opcional para tests)
        
    Returns:
        ChunkingResult con total y IDs de chunks creados
        
    Raises:
        ValueError: Si text_uri es inválido o texto vacío
        RuntimeError: Si falla la segmentación o persistencia
        
    Notas:
        - Idempotente: limpia chunks previos del mismo file_id
        - Valida constraints automáticos (token_count >= 0)
        - Usa transacción explícita (commit manejado externamente)
    """
    logger.info(
        "[chunk_text] Starting chunking phase",
        extra={
            "job_id": str(job_id),
            "file_id": str(file_id),
            "max_tokens": params.max_tokens,
            "overlap": params.overlap,
            "text_uri": text_uri,
        },
    )
    
    # Log event: phase started
    await rag_job_event_repository.log_event(
        db,
        job_id=job_id,
        event_type="phase_started",
        rag_phase=RagPhase.chunk,
        progress_pct=40,
        message=f"Starting chunking for file {file_id}",
    )
    
    try:
        # ========== VALIDACIÓN DE PARÁMETROS ==========
        
        if not text_uri or "/" not in text_uri:
            raise ValueError(f"Invalid text_uri format: '{text_uri}'. Expected 'bucket/path'")
        
        if not storage_client:
            raise ValueError("storage_client is required for chunking")
        
        # Parse text_uri: formato "bucket/path/to/file"
        parts = text_uri.split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid text_uri format: {text_uri}. Expected 'bucket/path'")
        
        bucket_name, storage_path = parts
        
        # ========== CARGAR TEXTO DESDE STORAGE ==========
        
        logger.info(f"[chunk_text] Downloading text from {bucket_name}/{storage_path}")
        
        try:
            text_bytes = await storage_client.download_file(bucket_name, storage_path)
        except Exception as storage_err:
            logger.error(f"[chunk_text] Failed to read from {text_uri}: {storage_err}")
            raise FileNotFoundError(f"Cannot read text_uri {text_uri}: {storage_err}") from storage_err
        
        text_content = text_bytes.decode('utf-8', errors='replace').strip()
        
        if not text_content:
            raise ValueError(f"Empty text content at {text_uri}")
        
        logger.info(
            "[chunk_text] Text loaded from storage",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "char_count": len(text_content),
                "text_uri": text_uri,
            },
        )
        
        # 2) Idempotencia: limpiar chunks previos
        existing_count = await chunk_metadata_repository.count_by_file(db, file_id)
        
        if existing_count > 0:
            logger.info(f"[chunk_text] Removing {existing_count} existing chunks for file_id={file_id}")
            await chunk_metadata_repository.delete_by_file(db, file_id)
            await db.flush()
        
        # 3) Segmentar texto
        logger.info(f"[chunk_text] Splitting text with max_tokens={params.max_tokens}, overlap={params.overlap}")
        chunks = _split_text_into_chunks(
            text_content,
            max_tokens=params.max_tokens,
            overlap=params.overlap,
        )
        
        if not chunks:
            raise RuntimeError("Text segmentation produced no chunks")
        
        logger.info(
            "[chunk_text] Text segmented into chunks",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "total_chunks": len(chunks),
                "max_tokens": params.max_tokens,
                "overlap": params.overlap,
            },
        )
        
        # 4) Persistir chunks con nombres de campos alineados con SQL
        chunk_records = []
        for idx, (chunk_text, token_count) in enumerate(chunks):
            chunk_records.append(ChunkMetadata(
                file_id=file_id,
                chunk_index=idx,
                chunk_text=chunk_text,
                token_count=token_count,
                metadata_json={},
            ))
        
        inserted_chunks = await chunk_metadata_repository.insert_chunks(db, chunk_records)
        await db.flush()
        
        chunk_ids = [c.chunk_id for c in inserted_chunks]
        
        logger.info(
            "[chunk_text] Chunks persisted to database",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "chunks_persisted": len(chunk_ids),
            },
        )
        
        # Log event: phase completed
        await rag_job_event_repository.log_event(
            db,
            job_id=job_id,
            event_type="phase_completed",
            rag_phase=RagPhase.chunk,
            progress_pct=50,
            message=f"Chunking completed: {len(chunk_ids)} chunks created",
        )
        
        return ChunkingResult(
            total_chunks=len(chunk_ids),
            chunk_ids=chunk_ids,
        )
        
    except Exception as e:
        logger.error(f"[chunk_text] Chunking failed: {e}", exc_info=True)
        
        # Log event: phase failed
        await rag_job_event_repository.log_event(
            db,
            job_id=job_id,
            event_type="phase_failed",
            rag_phase=RagPhase.chunk,
            progress_pct=40,
            message=f"Chunking failed: {str(e)}",
        )
        
        raise RuntimeError(f"Chunking failed: {str(e)}") from e


# Fin del archivo backend/app/modules/rag/facades/chunk_facade.py
