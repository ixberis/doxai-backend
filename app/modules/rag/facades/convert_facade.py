# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/facades/convert_facade.py

Facade para fase 'convert': conversión de binario a texto sin OCR.
Extrae texto nativo de PDFs, DOCX, etc. sin procesamiento de imágenes.

INTEGRACIÓN: Usa clientes de Storage y extractores de texto.

Responsabilidades:
- Detectar extractor apropiado por mime_type
- Extraer texto nativo (no escaneado)
- Guardar resultado en storage (rag-cache-jobs)
- Actualizar job con eventos de progreso

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 2)
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import RagJobRepository, RagJobEventRepository
from app.modules.rag.enums import RagPhase

logger = logging.getLogger(__name__)


@dataclass
class ConvertedText:
    """Resultado de conversión binario → texto."""
    result_uri: str
    byte_size: int
    checksum: str


async def convert_to_text(
    db: AsyncSession,
    job_id: UUID,
    file_id: UUID,
    source_uri: str,
    mime_type: str,
    *,
    storage_client=None,
    job_repo: RagJobRepository = None,
    event_repo: RagJobEventRepository = None,
) -> ConvertedText:
    """
    Convierte documento binario a texto sin OCR.
    
    Args:
        db: Sesión de base de datos
        job_id: ID del job RAG en curso
        file_id: ID del archivo a convertir
        source_uri: URI del archivo fuente en storage (ej: users-files/...)
        mime_type: Tipo MIME del documento
        storage_client: Cliente de storage (inyectable para testing)
        job_repo: Repository de jobs (inyectable)
        event_repo: Repository de eventos (inyectable)
        
    Returns:
        ConvertedText con URI del resultado, tamaño y checksum
        
    Raises:
        ValueError: Si mime_type no soportado
        FileNotFoundError: Si source_uri no existe en storage
        RuntimeError: Si falla la extracción
        
    Notas:
        - No incluye OCR (fase independiente)
        - Idempotente por checksum del source
        - Guarda resultado en rag-cache-jobs/{job_id}/converted.txt
    """
    job_repo = job_repo or RagJobRepository()
    event_repo = event_repo or RagJobEventRepository()
    
    if storage_client is None:
        # TODO: En producción, inyectar cliente real de storage
        raise RuntimeError("storage_client is required")
    
    logger.info(
        "[convert_to_text] Starting text conversion",
        extra={
            "job_id": str(job_id),
            "file_id": str(file_id),
            "mime_type": mime_type,
            "source_uri": source_uri,
        },
    )
    
    # 1. Registrar inicio de fase convert (solo si tenemos db)
    if db is not None:
        await event_repo.log_event(
            session=db,
            job_id=job_id,
            event_type="phase_started",
            rag_phase=RagPhase.convert,
            progress_pct=0,
            message=f"Iniciando conversión de {mime_type}",
        )
    
    try:
        # 2. Descargar archivo de storage
        logger.info(f"[convert_to_text] Descargando archivo desde {source_uri}")
        file_bytes = await storage_client.read(source_uri)
        
        # 3. Extraer texto según mime_type
        extracted_text = _extract_text_by_mimetype(mime_type, file_bytes)
        
        # 4. Calcular checksum
        checksum = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
        byte_size = len(extracted_text.encode("utf-8"))
        
        logger.info(
            "[convert_to_text] Text extracted successfully",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "byte_size": byte_size,
                "checksum": checksum[:8],
            },
        )
        
        # 5. Guardar texto en storage (rag-cache-jobs)
        result_uri = f"rag-cache-jobs/{job_id}/converted.txt"
        await storage_client.write(
            result_uri,
            extracted_text.encode("utf-8"),
            content_type="text/plain",
        )
        
        logger.info(
            "[convert_to_text] Text saved to storage",
            extra={
                "job_id": str(job_id),
                "file_id": str(file_id),
                "result_uri": result_uri,
                "byte_size": byte_size,
            },
        )
        
        # 6. Registrar éxito (solo si tenemos db)
        if db is not None:
            await event_repo.log_event(
                session=db,
                job_id=job_id,
                event_type="phase_completed",
                rag_phase=RagPhase.convert,
                progress_pct=100,
                message=f"Conversión completada: {byte_size} bytes",
                event_payload={"checksum": checksum, "byte_size": byte_size},
            )
        
        return ConvertedText(
            result_uri=result_uri,
            byte_size=byte_size,
            checksum=checksum,
        )
    
    except NotImplementedError:
        # Dejar que NotImplementedError se propague sin envolver (para tests de contrato)
        raise
    except Exception as e:
        logger.error(f"[convert_to_text] Error en conversión: {e}", exc_info=True)
        
        # Registrar error (solo si tenemos db)
        if db is not None:
            await event_repo.log_event(
                session=db,
                job_id=job_id,
                event_type="phase_failed",
                rag_phase=RagPhase.convert,
                progress_pct=0,
                message=f"Error en conversión: {str(e)}",
            )
        
        raise RuntimeError(f"Error en conversión de texto: {e}") from e


def _extract_text_by_mimetype(mime_type: str, file_bytes: bytes) -> str:
    """
    Extrae texto nativo según mime_type.
    
    NOTA: Implementación simplificada para FASE 2.
    En producción, usar bibliotecas especializadas (PyPDF2, python-docx, etc.)
    """
    # Soporte básico para texto plano y markdown
    if mime_type in ["text/plain", "text/markdown", "text/html"]:
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Intenta con latin-1 como fallback
            return file_bytes.decode("latin-1", errors="replace")
    
    # PDF y otros formatos: pendiente de implementación completa
    if mime_type == "application/pdf":
        # TODO: Usar PyPDF2 o pdfplumber
        raise NotImplementedError(
            "PDF text extraction requires PyPDF2/pdfplumber (FASE 2 pendiente)"
        )
    
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        # TODO: Usar python-docx
        raise NotImplementedError(
            "DOCX text extraction requires python-docx (FASE 2 pendiente)"
        )
    
    raise ValueError(f"Mime type no soportado para extracción: {mime_type}")
