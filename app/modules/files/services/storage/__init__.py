
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/__init__.py

Módulo de storage optimizado con:
- Connection pooling
- Compresión automática  
- Cache mejorado con métricas
- Múltiples niveles de cache (L1: memoria, L2: disco opcional)

Componentes principales:
- DownloadCache: Cache compatible con versión básica y mejorada
- StoragePathsService: Gestión de rutas de storage
- FileDownloadStorage, FileUploadStorage: Operaciones de archivos
- EnhancedCache (opcional): Cache multinivel con métricas
- CompressionService (opcional): Compresión inteligente

Autor: Ixchel Beristain / DoxAI
Actualizado: 05/11/2025
"""

from .download_cache import DownloadCache
from .storage_paths import StoragePathsService
from .storage_migration_service import StorageMigrationService
from .file_list_storage import FileListStorage
from .file_download_storage import FileDownloadStorage
from .file_get_url_storage import FileGetUrlStorage
from .safe_filename import make_safe_storage_filename

# Servicios optimizados (opcional - para producción)
try:
    from .enhanced_cache import EnhancedCache
    from .cache_metrics import CacheMetrics
    from .compression_service import CompressionService, get_compression_service
    OPTIMIZATIONS_AVAILABLE = True
except ImportError:
    OPTIMIZATIONS_AVAILABLE = False

__all__ = [
    "DownloadCache",
    "StoragePathsService",
    "StorageMigrationService",
    "FileListStorage",
    "FileDownloadStorage",
    "FileGetUrlStorage",
    "make_safe_storage_filename",
]

if OPTIMIZATIONS_AVAILABLE:
    __all__.extend([
        "EnhancedCache",
        "CacheMetrics",
        "CompressionService",
        "get_compression_service",
    ])

# Fin del archivo backend\app\modules\files\services\storage\__init__.py






