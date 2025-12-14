# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/facades/embed_facade.py

Facade para fase 'embed': generación y persistencia de embeddings.
Genera vectores y persiste en DocumentEmbedding con pgvector.

INTEGRACIÓN: Usa OpenAI Embeddings Client + DocumentEmbeddingRepository.

Responsabilidades:
- Generar embeddings para chunks seleccionados
- Persistir en DocumentEmbedding (vector 1536d, metadatos)
- Manejar file_category, is_active
- Idempotencia por (file_id, chunk_index, embedding_model, dimension)

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 2)
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import (
    RagJobRepository,
    RagJobEventRepository,
    ChunkMetadataRepository,
    DocumentEmbeddingRepository,
    document_embedding_repository,
)
from app.modules.rag.models import DocumentEmbedding
from app.modules.rag.enums import RagPhase, FileCategory
from app.shared.integrations.openai_embeddings_client import generate_embeddings as openai_generate_embeddings

logger = logging.getLogger(__name__)


@dataclass
class ChunkSelector:
    """Selector de chunks a embeddear."""
    chunk_ids: list[UUID] | None = None
    index_range: tuple[int, int] | None = None  # (start, end) inclusive


@dataclass
class EmbeddingResult:
    """Resultado de operación de embedding."""
    total_chunks: int
    embedded: int
    
    @property
    def skipped(self) -> int:
        """Chunks omitidos (calculado como total_chunks - embedded)."""
        return self.total_chunks - self.embedded


async def generate_embeddings(
    db: AsyncSession,
    job_id: UUID,
    file_id: UUID,
    embedding_model: str,
    selector: ChunkSelector,
    *,
    dimension: int = 1536,
    openai_api_key: str = None,
    job_repo: RagJobRepository = None,
    event_repo: RagJobEventRepository = None,
    chunk_repo: ChunkMetadataRepository = None,
    embedding_repo: DocumentEmbeddingRepository = None,
) -> EmbeddingResult:
    """
    Genera embeddings y persiste en DocumentEmbedding.
    
    Args:
        db: Sesión de base de datos
        job_id: ID del job RAG en curso
        file_id: ID del archivo fuente
        embedding_model: Modelo a usar (ej: text-embedding-3-large)
        selector: Selector de chunks (por IDs o rango de índices)
        dimension: Dimensión del vector (default 1536, fijado en ORM)
        openai_api_key: API key de OpenAI (inyectable)
        job_repo: Repository de jobs (inyectable)
        event_repo: Repository de eventos (inyectable)
        chunk_repo: Repository de chunks (inyectable)
        embedding_repo: Repository de embeddings (inyectable)
        
    Returns:
        EmbeddingResult con conteo de chunks procesados
        
    Raises:
        RuntimeError: Si openai_api_key no está configurado
        ValueError: Si selector inválido o chunks no encontrados
        
    Contrato ORM (campos mínimos a persistir en DocumentEmbedding):
        - file_id: UUID (NOT NULL)
        - file_category: FileCategory (INPUT/OUTPUT, NOT NULL)
        - rag_phase: RagPhase (nullable, fase del pipeline)
        - source_type: str (default "document")
        - chunk_index: int (NOT NULL, único con file_id+embedding_model)
        - text_chunk: str (NOT NULL)
        - token_count: int (nullable, >= 0 si presente)
        - source_page: int (nullable, >= 0 si presente)
        - vector: Vector(1536) (NOT NULL, dimensión fija)
        - embedding_model: str (NOT NULL)
        - is_active: bool (default True)
        
    Notas:
        - Idempotente por (file_id, chunk_index, embedding_model)
        - Dimensión fija 1536 en BD (valida contra param si difiere)
        - Respeta fase del pipeline en rag_phase para trazabilidad
    """
    job_repo = job_repo or RagJobRepository()
    event_repo = event_repo or RagJobEventRepository()
    chunk_repo = chunk_repo or ChunkMetadataRepository()
    embedding_repo = embedding_repo or document_embedding_repository
    
    # FASE 3 - Issue #30: Validar que dimension == 1536 (fijado en SQL)
    if dimension != 1536:
        raise ValueError(
            f"dimension must be 1536 to match SQL schema vector(1536), got {dimension}"
        )
    
    if not openai_api_key:
        raise RuntimeError("openai_api_key is required for embeddings")
    
    logger.info(
        "[generate_embeddings] Starting embedding generation",
        extra={
            "job_id": str(job_id),
            "file_id": str(file_id),
            "embedding_model": embedding_model,
            "dimension": dimension,
        },
    )
    
    # 1. Registrar inicio de fase embed
    await event_repo.log_event(
        db=db,
        job_id=job_id,
        event_type="phase_started",
        rag_phase=RagPhase.embed,
        progress_pct=0,
        message=f"Iniciando generación de embeddings con {embedding_model}",
    )
    
    try:
        # 2. Seleccionar chunks según selector
        total_file_chunks = 0
        if selector.chunk_ids:
            # Selección por IDs específicos
            chunks = []
            for chunk_id in selector.chunk_ids:
                chunk = await chunk_repo.get_by_id(db, chunk_id)
                if chunk:
                    chunks.append(chunk)
            total_file_chunks = len(chunks)
        elif selector.index_range:
            # Selección por rango de índices
            start, end = selector.index_range
            all_chunks = await chunk_repo.list_by_file(db, file_id)
            chunks = [c for c in all_chunks if start <= c.chunk_index <= end]
            # total_chunks debe reflejar todos los chunks del archivo, no solo el rango
            total_file_chunks = len(all_chunks)
        else:
            # Sin selector: todos los chunks del archivo
            chunks = await chunk_repo.list_by_file(db, file_id)
            total_file_chunks = len(chunks)

        if not chunks:
            logger.warning(f"[generate_embeddings] No se encontraron chunks para file_id={file_id} y/o para el selector proporcionado")
            # Aun si el rango no coincide, total_chunks debe reflejar todos los chunks del archivo
            all_chunks_for_count = await chunk_repo.list_by_file(db, file_id)
            return EmbeddingResult(total_chunks=len(all_chunks_for_count), embedded=0)
        
        logger.info(
            "[generate_embeddings] Chunks selected for embedding",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "total_chunks": len(chunks),
            },
        )
        
        # 3. Filtrar chunks ya embebidos (idempotencia)
        chunks_to_embed = []
        for chunk in chunks:
            exists = await embedding_repo.exists_for_file_and_chunk(
                db, file_id, chunk.chunk_index, embedding_model
            )
            if not exists:
                chunks_to_embed.append(chunk)
        
        skipped = len(chunks) - len(chunks_to_embed)
        logger.info(
            "[generate_embeddings] Chunks filtered for embedding",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "chunks_to_embed": len(chunks_to_embed),
                "chunks_skipped": skipped,
            },
        )
        
        if not chunks_to_embed:
            await event_repo.log_event(
                db=db,
                job_id=job_id,
                event_type="phase_completed",
                rag_phase=RagPhase.embed,
                progress_pct=100,
                message="Todos los chunks ya tenían embeddings",
            )
            return EmbeddingResult(
                total_chunks=total_file_chunks,
                embedded=0,
            )
        
        # 4. Extraer textos de los chunks
        texts = [chunk.chunk_text for chunk in chunks_to_embed]
        
        # 5. Generar embeddings con OpenAI
        logger.info(f"[generate_embeddings] Llamando a OpenAI API...")
        vectors = await openai_generate_embeddings(
            texts,
            api_key=openai_api_key,
            model=embedding_model,
            dimension=dimension,
        )
        
        logger.info(
            "[generate_embeddings] Embeddings generated by OpenAI",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "vectors_generated": len(vectors),
                "embedding_model": embedding_model,
                "dimension": dimension,
            },
        )
        
        # 6. Persistir embeddings en DocumentEmbedding
        embeddings_to_insert = []
        for chunk, vector in zip(chunks_to_embed, vectors):
            embedding = DocumentEmbedding(
                file_id=file_id,
                chunk_id=chunk.chunk_id,
                file_category=FileCategory.INPUT,  # Asumimos INPUT por defecto
                rag_phase=RagPhase.embed,
                chunk_index=chunk.chunk_index,
                embedding_vector=vector,
                embedding_model=embedding_model,
                is_active=True,
            )
            embeddings_to_insert.append(embedding)
        
        inserted = await embedding_repo.insert_embeddings(db, embeddings_to_insert)
        await db.commit()
        
        logger.info(
            "[generate_embeddings] Embeddings persisted to database",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "embeddings_persisted": len(inserted),
                "embedding_model": embedding_model,
            },
        )
        
        # 7. Registrar éxito
        await event_repo.log_event(
            db=db,
            job_id=job_id,
            event_type="phase_completed",
            rag_phase=RagPhase.embed,
            progress_pct=100,
            message=f"Embeddings generados: {len(inserted)} chunks embebidos",
            event_payload={
                "embedded": len(inserted),
                "skipped": skipped,
                "model": embedding_model,
                "dimension": dimension,
            },
        )
        
        return EmbeddingResult(
            total_chunks=total_file_chunks,
            embedded=len(inserted),
        )
    
    except Exception as e:
        logger.error(f"[generate_embeddings] Error: {e}", exc_info=True)
        
        # Registrar error
        await event_repo.log_event(
            db=db,
            job_id=job_id,
            event_type="phase_failed",
            rag_phase=RagPhase.embed,
            progress_pct=0,
            message=f"Error en generación de embeddings: {str(e)}",
        )
        
        raise RuntimeError(f"Error en generación de embeddings: {e}") from e
