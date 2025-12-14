
# -*- coding: utf-8 -*-
"""
backend/app/shared/core/resource_cache.py

Punto de entrada principal para gestión de recursos del pipeline RAG.
Re-exporta funcionalidad desde módulos especializados más pequeños.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 06/09/2025: Sistema de warm-up robusto + singletons
- 07/09/2025: Cierre blindado de recursos en shutdown_all()
- 2025-10-18: Migrado a app.shared.core
- 2025-10-24: Refactorizado en módulos especializados para mejor mantenibilidad
"""

# Re-exportar dataclasses y estado
from .warmup_status_cache import WarmupStatus
from .resources_cache import (
    GlobalResources,
    resources,
    get_warmup_status,
)

# Re-exportar verificación de herramientas del sistema
from .system_tools_cache import (
    check_tesseract_availability,
    check_ghostscript_availability,
    check_poppler_availability,
)

# Re-exportar singletons de modelos
from .model_singletons_cache import (
    quiet_pdf_parsers,
    get_warmup_asset_path,
    get_singleton_table_agent,
    get_table_agent,
    get_fast_parser,
    get_standard_language_config,
    warmup_unstructured,
    ensure_table_model_loaded,
)

# Re-exportar gestión de cliente HTTP
from .http_client_cache import (
    create_http_client,
    get_http_client,
)

# Re-exportar utilidades de reintentos HTTP
from .http_retry_utils import (
    retry_with_backoff,
    retry_get_with_backoff,
    retry_post_with_backoff,
)

# Re-exportar orquestación de warm-up
from .warmup_orchestrator_cache import (
    run_warmup_once,
    warmup_all,
)

# Re-exportar lifecycle management
from .resource_lifecycle_cache import shutdown_all

# Exportar API pública
__all__ = [
    # Estado y dataclasses
    "WarmupStatus",
    "GlobalResources",
    "resources",
    "get_warmup_status",
    # Verificación de herramientas
    "check_tesseract_availability",
    "check_ghostscript_availability",
    "check_poppler_availability",
    # Singletons de modelos
    "quiet_pdf_parsers",
    "get_warmup_asset_path",
    "get_singleton_table_agent",
    "get_table_agent",
    "get_fast_parser",
    "get_standard_language_config",
    "warmup_unstructured",
    "ensure_table_model_loaded",
    # Cliente HTTP
    "create_http_client",
    "get_http_client",
    # Reintentos HTTP con backoff
    "retry_with_backoff",
    "retry_get_with_backoff",
    "retry_post_with_backoff",
    # Warm-up
    "run_warmup_once",
    "warmup_all",
    # Lifecycle
    "shutdown_all",
]

# Fin del archivo backend/app/shared/core/resource_cache.py






