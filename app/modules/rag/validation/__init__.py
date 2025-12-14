# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/tests/test_services.py

Tests unitarios para servicios del módulo RAG.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.modules.rag.services.indexing_service import IndexingService
from app.modules.rag.services.embedding_service import EmbeddingService
from app.modules.rag.services.chunking_service import ChunkingService
from app.modules.rag.schemas.indexing_schemas import (
    IndexingJobCreate,
    EmbeddingCreate,
    ChunkCreate,
)
from app.modules.projects.models.project_models import Project
from app.modules.auth.models.user_models import User
from app.modules.files.models.input_file_models import InputFile
from app.modules.rag.models.embedding_models import DocumentEmbedding
from app.modules.rag.models.chunk_models import ChunkMetadata
from app.modules.rag.enums.rag_phase_enum import RagJobPhase
from app.modules.rag.enums.file_category_enum import FileCategory


class TestIndexingService:
    """Tests para IndexingService."""
    
    def test_create_indexing_job_success(
        self, 
        db: Session, 
        sample_project: Project,
        sample_user: User
    ):
        """Test: crear job de indexación exitosamente."""
        service = IndexingService(db)
        
        job_data = IndexingJobCreate(
            project_id=sample_project.project_id,
            filename=None,
            user_id=sample_user.user_id
        )
        
        result = service.create_indexing_job(job_data)
        
        assert result.project_id == sample_project.project_id
        assert result.started_by == sample_user.user_id
        assert result.phase == RagJobPhase.QUEUED
        assert result.job_id is not None
    
    def test_create_indexing_job_project_not_found(
        self, 
        db: Session,
        sample_user: User
    ):
        """Test: error al crear job para proyecto inexistente."""
        service = IndexingService(db)
        
        job_data = IndexingJobCreate(
            project_id=uuid4(),
            filename=None,
            user_id=sample_user.user_id
        )
        
        with pytest.raises(HTTPException) as exc_info:
            service.create_indexing_job(job_data)
        
        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()
    
    def test_list_project_jobs(
        self, 
        db: Session, 
        sample_project: Project
    ):
        """Test: listar jobs de un proyecto."""
        service = IndexingService(db)
        
        result = service.list_project_jobs(sample_project.project_id)
        
        assert isinstance(result, list)


class TestEmbeddingService:
    """Tests para EmbeddingService."""
    
    def test_create_embedding_success(
        self, 
        db: Session, 
        sample_input_file: InputFile
    ):
        """Test: crear embedding exitosamente."""
        service = EmbeddingService(db)
        
        test_vector = [0.1] * 1536
        
        embedding_data = EmbeddingCreate(
            document_file_id=sample_input_file.input_file_id,
            chunk_index=0,
            text_chunk="Test chunk for embedding",
            vector=test_vector,
            embedding_model="text-embedding-3-large",
            token_count=5,
            source_page=1
        )
        
        result = service.create_embedding(embedding_data, FileCategory.INPUT_FILE)
        
        assert result.document_file_id == sample_input_file.input_file_id
        assert result.chunk_index == 0
        assert result.embedding_model == "text-embedding-3-large"
    
    def test_list_file_embeddings(
        self, 
        db: Session, 
        sample_input_file: InputFile,
        sample_embedding: DocumentEmbedding
    ):
        """Test: listar embeddings de un archivo."""
        service = EmbeddingService(db)
        
        result = service.list_file_embeddings(sample_input_file.input_file_id)
        
        assert len(result) == 1
        assert result[0].document_file_id == sample_input_file.input_file_id
    
    def test_delete_file_embeddings(
        self, 
        db: Session, 
        sample_input_file: InputFile,
        sample_embedding: DocumentEmbedding
    ):
        """Test: eliminar embeddings de un archivo."""
        service = EmbeddingService(db)
        
        count = service.delete_file_embeddings(sample_input_file.input_file_id)
        
        assert count == 1
        
        # Verificar que se marcó como inactivo
        db.refresh(sample_embedding)
        assert sample_embedding.is_active is False
        assert sample_embedding.deleted_at is not None


class TestChunkingService:
    """Tests para ChunkingService."""
    
    def test_create_chunk_success(
        self, 
        db: Session, 
        sample_input_file: InputFile
    ):
        """Test: crear chunk exitosamente."""
        service = ChunkingService(db)
        
        chunk_data = ChunkCreate(
            document_file_id=sample_input_file.input_file_id,
            chunk_index=0,
            text_content="Test chunk content for chunking service",
            token_count=8,
            source_page_start=1,
            source_page_end=1,
            chunk_type="paragraph",
            metadata={"test": True}
        )
        
        result = service.create_chunk(chunk_data)
        
        assert result.document_file_id == sample_input_file.input_file_id
        assert result.chunk_index == 0
        assert result.text_content == chunk_data.text_content
    
    def test_list_file_chunks(
        self, 
        db: Session, 
        sample_input_file: InputFile,
        sample_chunk: ChunkMetadata
    ):
        """Test: listar chunks de un archivo."""
        service = ChunkingService(db)
        
        result = service.list_file_chunks(sample_input_file.input_file_id)
        
        assert len(result) == 1
        assert result[0].document_file_id == sample_input_file.input_file_id
        assert result[0].chunk_index == 0
    
    def test_get_chunk_success(
        self, 
        db: Session,
        sample_chunk: ChunkMetadata
    ):
        """Test: obtener chunk por ID."""
        service = ChunkingService(db)
        
        result = service.get_chunk(sample_chunk.chunk_id)
        
        assert result.chunk_id == sample_chunk.chunk_id
        assert result.document_file_id == sample_chunk.document_file_id
    
    def test_get_chunk_not_found(
        self, 
        db: Session
    ):
        """Test: error al obtener chunk inexistente."""
        service = ChunkingService(db)
        
        with pytest.raises(HTTPException) as exc_info:
            service.get_chunk(uuid4())
        
        assert exc_info.value.status_code == 404

