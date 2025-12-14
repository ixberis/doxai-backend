# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_eviction.py

**CONFIGURACIÓN DE EVICCIÓN DE CACHÉ (FASE 2)**

Settings específicos para el sistema de limpieza automática de caché.

Autor: DoxAI
Fecha: 29 de septiembre de 2025 (FASE 2)
Migrado: 2025-10-18 a shared/config
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheEvictionSettings(BaseSettings):
    """
    Configuración para evicción automática de caché (FASE 2).
    
    Controla el comportamiento del sistema de limpieza periódica
    de entradas de caché expiradas.
    """
    
    # Buckets dedicados (Opción B por defecto)
    pages_bucket: str = Field(
        default="rag-cache-pages",
        description="Bucket de Supabase Storage para páginas OCR"
    )
    
    pages_prefix: str = Field(
        default="",
        description="Prefijo opcional dentro del bucket de páginas"
    )
    
    jobs_bucket: str = Field(
        default="rag-cache-jobs",
        description="Bucket de Supabase Storage para job states"
    )
    
    jobs_prefix: str = Field(
        default="",
        description="Prefijo opcional dentro del bucket de jobs"
    )
    
    # TTL (fallback cuando no hay expires_at)
    ttl_ocr_results: int = Field(
        default=604800,
        ge=3600,
        le=7776000,
        description="TTL en segundos para resultados OCR (default: 7 días)"
    )
    
    ttl_jobs: int = Field(
        default=86400,
        ge=3600,
        le=604800,
        description="TTL en segundos para job states (default: 1 día)"
    )
    
    # Paginación
    page_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Número de archivos a procesar por página"
    )
    
    max_pages: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Máximo número de páginas a procesar por ejecución"
    )
    
    # Timeouts
    max_execution_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Tiempo máximo de ejecución en segundos (5 min default)"
    )
    
    # Batch deletion
    delete_batch_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Número de archivos a eliminar por batch"
    )
    
    # Thresholds
    threshold_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Días de threshold para archivos sin expires_at"
    )
    
    # Ejecución
    enabled: bool = Field(
        default=True,
        description="Habilitar/deshabilitar limpieza automática"
    )
    
    dry_run_default: bool = Field(
        default=False,
        description="Ejecutar en modo dry-run por defecto (no elimina)"
    )
    
    # Logging
    log_progress_every_n_pages: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Log de progreso cada N páginas"
    )
    
    log_individual_deletions: bool = Field(
        default=False,
        description="Log individual de cada archivo eliminado (verbose)"
    )
    
    # Métricas
    save_metrics_to_db: bool = Field(
        default=True,
        description="Guardar métricas de limpieza en base de datos"
    )
    
    metrics_retention_days: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Días de retención de métricas de limpieza"
    )
    
    # Cron schedule (informativo, el schedule real está en SQL migration)
    pages_schedule: str = Field(
        default="0 3 * * *",  # Diario 3:00 AM
        description="Schedule cron para limpieza de páginas"
    )
    
    jobs_schedule: str = Field(
        default="0 4 * * 0",  # Semanal domingo 4:00 AM
        description="Schedule cron para limpieza de job states"
    )
    
    model_config = SettingsConfigDict(
        env_prefix="CACHE_EVICTION_",
        case_sensitive=False
    )


__all__ = ['CacheEvictionSettings']







