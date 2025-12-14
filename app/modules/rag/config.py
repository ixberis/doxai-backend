# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/config.py

Configuración del módulo RAG (indexación y búsqueda).

Autor: DoxAI
Fecha: 2025-10-28
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class RagConfig(BaseSettings):
    """
    Configuración para el módulo RAG.
    
    Variables de entorno:
        # Azure OCR
        AZURE_OCR_ENDPOINT: Endpoint de Azure Cognitive Services
        AZURE_OCR_KEY: API key de Azure
        AZURE_OCR_STRATEGY_DEFAULT: Estrategia por defecto (fast/accurate/balanced)
        
        # Embeddings
        EMBEDDINGS_PROVIDER: Proveedor de embeddings (openai/azure)
        EMBEDDINGS_API_KEY: API key del proveedor
        EMBEDDINGS_ENDPOINT: Endpoint (para Azure)
        EMBEDDINGS_MODEL_DEFAULT: Modelo por defecto
        EMBEDDINGS_DIMENSION_DEFAULT: Dimensión por defecto del vector
        
        # Chunking
        CHUNK_MAX_TOKENS_DEFAULT: Máximo de tokens por chunk
        CHUNK_OVERLAP_DEFAULT: Overlap entre chunks (en tokens)
        
        # Storage
        STORAGE_BACKEND: Backend de almacenamiento (supabase/local)
        STORAGE_BUCKET_NAME: Nombre del bucket
        STORAGE_BASE_PATH: Path base (para local)
    """
    
    # Azure OCR
    azure_ocr_endpoint: Optional[str] = None
    azure_ocr_key: Optional[str] = None
    azure_ocr_strategy_default: str = "balanced"
    
    # Embeddings
    embeddings_provider: str = "openai"
    embeddings_api_key: Optional[str] = None
    embeddings_endpoint: str = "https://api.openai.com/v1"
    embeddings_model_default: str = "text-embedding-3-large"
    embeddings_dimension_default: int = 1536
    
    # Chunking
    chunk_max_tokens_default: int = 512
    chunk_overlap_default: int = 50
    
    # Storage
    storage_backend: str = "supabase"
    storage_bucket_name: str = "documents"
    storage_base_path: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAG_",
        case_sensitive=False
    )


# Instancia global de configuración
rag_config = RagConfig()
