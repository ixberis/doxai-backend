# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/facades/ocr_facade.py

Facade para fase 'ocr': OCR explícito con Azure Cognitive Services.
Fase independiente de 'convert' para documentos escaneados o imágenes.

INTEGRACIÓN: Usa AzureDocumentIntelligenceClient + Storage.

Responsabilidades:
- Ejecutar OCR con estrategia configurable (fast/accurate/balanced)
- Extraer texto de documentos escaneados o imágenes
- Detectar idioma y confianza del resultado
- Guardar resultado en storage y actualizar eventos de job

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 2)
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import RagJobRepository, RagJobEventRepository
from app.modules.rag.enums import RagPhase, OcrOptimization
from app.shared.integrations.azure_document_intelligence import (
    AzureDocumentIntelligenceClient,
    AzureOcrResult as AzureOcrResultExt,
)

logger = logging.getLogger(__name__)


@dataclass
class OcrText:
    """Resultado de OCR con metadatos de calidad."""
    result_uri: str
    total_pages: int = 0
    lang: str | None = None
    confidence: float | None = None


async def run_ocr(
    db: AsyncSession,
    job_id: UUID,
    file_id: UUID,
    source_uri: str,
    strategy: OcrOptimization | str = OcrOptimization.balanced,
    *,
    azure_client: AzureDocumentIntelligenceClient = None,
    storage_client=None,
    job_repo: RagJobRepository = None,
    event_repo: RagJobEventRepository = None,
) -> OcrText:
    """
    Ejecuta OCR sobre documento escaneado o imagen.
    
    Args:
        db: Sesión de base de datos
        job_id: ID del job RAG en curso
        file_id: ID del documento a procesar
        source_uri: URI del archivo fuente (PDF/imagen) con acceso público
        strategy: Estrategia de optimización (fast/accurate/balanced)
        azure_client: Cliente de Azure Document Intelligence (inyectable)
        storage_client: Cliente de storage (inyectable)
        job_repo: Repository de jobs (inyectable)
        event_repo: Repository de eventos (inyectable)
        
    Returns:
        OcrText con URI del resultado, idioma detectado y confianza
        
    Raises:
        RuntimeError: Si azure_client o storage_client no están configurados
        ValueError: Si strategy inválida
        TimeoutError: Si Azure OCR tarda demasiado
        
    Notas:
        - Usa Azure Cognitive Services (Document Intelligence)
        - Fase explícita e independiente (métricas claras)
        - Idempotente por (source_uri, strategy)
        - Guarda resultado en rag-cache-pages/{job_id}/ocr_result.txt
    """
    job_repo = job_repo or RagJobRepository()
    event_repo = event_repo or RagJobEventRepository()
    
    # ========== VALIDACIÓN DE PARÁMETROS ==========
    
    if not source_uri or "/" not in source_uri:
        raise ValueError(f"Invalid source_uri format: '{source_uri}'. Expected valid URI or 'bucket/path'")
    
    if azure_client is None:
        raise RuntimeError("azure_client is required for OCR")
    
    if storage_client is None:
        raise RuntimeError("storage_client is required")
    
    # Normalizar strategy
    if isinstance(strategy, str):
        try:
            strategy = OcrOptimization(strategy)
        except ValueError:
            raise ValueError(f"Estrategia OCR inválida: {strategy}")
    
    logger.info(
        "[run_ocr] Starting OCR phase",
        extra={
            "job_id": str(job_id),
            "file_id": str(file_id),
            "strategy": strategy.value,
            "source_uri": source_uri,
        },
    )
    
    # 1. Registrar inicio de fase OCR
    await event_repo.log_event(
        db=db,
        job_id=job_id,
        event_type="phase_started",
        rag_phase=RagPhase.ocr,
        progress_pct=0,
        message=f"Iniciando OCR con estrategia {strategy.value}",
    )
    
    try:
        # 2. Ejecutar OCR con Azure
        logger.info(f"[run_ocr] Llamando a Azure Document Intelligence...")
        azure_result: AzureOcrResultExt = await azure_client.analyze_document(
            file_uri=source_uri,
            strategy=strategy.value,
        )
        
        logger.info(
            "[run_ocr] OCR completed successfully",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "char_count": len(azure_result.text),
                "page_count": len(azure_result.pages),
                "confidence": azure_result.confidence,
                "lang": azure_result.lang,
            },
        )
        
        # 3. Guardar resultado en storage
        result_uri = f"rag-cache-pages/{job_id}/ocr_result.txt"
        await storage_client.write(
            result_uri,
            azure_result.text.encode("utf-8"),
            content_type="text/plain",
        )
        
        logger.info(
            "[run_ocr] OCR result saved to storage",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "result_uri": result_uri,
            },
        )
        
        # 4. Registrar éxito
        await event_repo.log_event(
            db=db,
            job_id=job_id,
            event_type="phase_completed",
            rag_phase=RagPhase.ocr,
            progress_pct=100,
            message=f"OCR completado: {len(azure_result.text)} chars extraídos",
            event_payload={
                "pages": len(azure_result.pages),
                "confidence": azure_result.confidence,
                "lang": azure_result.lang,
                "model_used": azure_result.model_used,
            },
        )
        
        return OcrText(
            result_uri=result_uri,
            total_pages=len(azure_result.pages),
            lang=azure_result.lang,
            confidence=azure_result.confidence,
        )
    
    except Exception as e:
        logger.error(f"[run_ocr] Error en OCR: {e}", exc_info=True)
        
        # Registrar error
        await event_repo.log_event(
            db=db,
            job_id=job_id,
            event_type="phase_failed",
            rag_phase=RagPhase.ocr,
            progress_pct=0,
            message=f"Error en OCR: {str(e)}",
        )
        
        raise RuntimeError(f"Error en OCR: {e}") from e
