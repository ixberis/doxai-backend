# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/cache/__init__.py

Exporta el sistema de caché de metadatos.
"""

from .metadata_cache import MetadataCache, get_metadata_cache, reset_global_cache

__all__ = ["MetadataCache", "get_metadata_cache", "reset_global_cache"]
