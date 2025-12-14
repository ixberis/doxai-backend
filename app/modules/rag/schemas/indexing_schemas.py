# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/schemas/indexing_schemas.py

Schemas Pydantic para operaciones de indexación RAG.

ACTUALIZADO v2: Usa file_id en lugar de document_file_id.

Autor: DoxAI
Fecha: 2025-10-18 (actualizado 2025-11-28)
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, field_serializer

from app.modules.rag.enums import RagJobPhase, RagPhase


# ==================== HELPERS ====================

def _to_datetime_utc(v: Any) -> Optional[datetime]:
    """Convierte timestamp/iso/epoch a datetime UTC; deja None si viene None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str):
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError(f"Cannot convert {type(v)} to datetime")


# ==================== INDEXING JOB SCHEMAS ====================

class IndexingJobCreate(BaseModel):
    """
    Schema para crear un job de indexación.
    """
    project_id: UUID
    file_id: UUID
    user_id: UUID
    mime_type: Optional[str] = None
    needs_ocr: bool = False


class JobProgressEvent(BaseModel):
    """
    Evento en el timeline de un job de indexación.
    """
    phase: RagPhase
    message: Optional[str] = None
    progress_pct: Optional[int] = None
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created_at(cls, v):
        return _to_datetime_utc(v)

    @field_serializer("created_at")
    def _ser_created_at(self, v: Optional[datetime]):
        return None if v is None else v.astimezone(timezone.utc).isoformat()

    @field_serializer("phase")
    def _ser_phase(self, v: RagPhase):
        return v.value


class JobProgressResponse(BaseModel):
    """
    Estado actual de un job de indexación.
    """
    job_id: UUID
    project_id: UUID
    file_id: Optional[UUID] = None
    phase: RagPhase
    status: Optional[RagJobPhase] = None
    progress_pct: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    event_count: int = 0
    timeline: list[JobProgressEvent] = Field(default_factory=list)

    @field_validator("started_at", "finished_at", "updated_at", mode="before")
    @classmethod
    def _coerce_dates(cls, v):
        return _to_datetime_utc(v)

    @field_serializer("started_at", "finished_at", "updated_at")
    def _ser_dates(self, v: Optional[datetime]):
        return None if v is None else v.astimezone(timezone.utc).isoformat()

    @field_serializer("phase")
    def _ser_phase(self, v: RagPhase):
        return v.value
    
    @field_serializer("status")
    def _ser_status(self, v: Optional[RagJobPhase]):
        return None if v is None else v.value


class IndexingJobResponse(BaseModel):
    """
    Respuesta al crear un job de indexación.
    """
    job_id: UUID
    project_id: UUID
    started_by: UUID
    phase: RagJobPhase
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _coerce_dates(cls, v):
        return _to_datetime_utc(v)

    @field_serializer("created_at", "updated_at")
    def _ser_dates(self, v: datetime):
        return v.astimezone(timezone.utc).isoformat()
    
    @field_serializer("phase")
    def _ser_phase(self, v: RagJobPhase):
        return v.value


# ==================== CHUNK SCHEMAS ====================

class ChunkCreate(BaseModel):
    """
    Schema para crear un chunk.
    """
    file_id: UUID
    chunk_index: int
    text_content: str
    token_count: Optional[int] = None
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    chunk_type: str = "paragraph"
    metadata: Optional[Dict[str, Any]] = None


class ChunkResponse(BaseModel):
    """
    Schema de respuesta para un chunk.
    """
    chunk_id: UUID
    file_id: UUID
    chunk_index: int
    text_content: str
    token_count: Optional[int] = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created_at(cls, v):
        return _to_datetime_utc(v)

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime):
        return v.astimezone(timezone.utc).isoformat()


# ==================== EMBEDDING SCHEMAS ====================

class EmbeddingCreate(BaseModel):
    """
    Schema para crear un embedding.
    """
    file_id: UUID
    chunk_index: int
    text_chunk: str
    vector: list[float]
    embedding_model: str
    token_count: Optional[int] = None
    source_page: Optional[int] = None
    rag_phase: Optional[RagPhase] = None
    source_type: str = Field(default="document")
    is_active: bool = Field(default=True)


class EmbeddingResponse(BaseModel):
    """
    Schema de respuesta para un embedding.
    """
    embedding_id: UUID
    file_id: UUID
    chunk_index: int
    embedding_model: str
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created_at(cls, v):
        return _to_datetime_utc(v)

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime):
        return v.astimezone(timezone.utc).isoformat()

# Fin del archivo backend/app/modules/rag/schemas/indexing_schemas.py
