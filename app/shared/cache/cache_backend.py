# -*- coding: utf-8 -*-
"""
backend/app/shared/cache/cache_backend.py

Interfaz base (ABC) para backends de caché.

Define el contrato que deben cumplir todas las implementaciones de caché
(MetadataCache, futuro RedisCacheBackend, etc.) para garantizar consistencia
en operaciones, métricas y cleanup.

Autor: DoxAI
Fecha: 2025-12-27
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, TypeVar

T = TypeVar("T")


class CacheBackend(ABC):
    """
    Interfaz abstracta para backends de caché.
    
    Todas las implementaciones de caché deben heredar de esta clase
    e implementar los métodos abstractos para garantizar:
    - Operaciones consistentes (get, set, invalidate, cleanup)
    - Métricas estandarizadas (get_stats)
    - Configuración uniforme (max_size, default_ttl)
    
    Arquitectura:
    Esta interfaz define el contrato para cachés L1 (in-memory por proceso)
    y L2 (distribuido, ej: Redis). Implementaciones actuales:
    - MetadataCache: L1 para Files
    Futuras implementaciones:
    - RedisCacheBackend: L2 para RAG y casos distribuidos
    
    Propiedades esperadas:
    - max_size: Tamaño máximo del caché (None = sin límite)
    - default_ttl: TTL por defecto en segundos (None = no expira por defecto)
    
    Métricas esperadas en get_stats():
    - size: Entradas actuales
    - hits: Aciertos
    - misses: Fallos
    - evictions: Evictions por LRU/capacidad
    - invalidations: Eliminaciones explícitas
    - expired_removals: Eliminaciones por TTL expirado
    - hit_rate_percent: Tasa de aciertos
    - total_requests: Total de requests
    """

    @property
    @abstractmethod
    def max_size(self) -> Optional[int]:
        """Tamaño máximo del caché. None si no tiene límite."""
        ...

    @property
    @abstractmethod
    def default_ttl(self) -> Optional[int]:
        """TTL por defecto en segundos. None si las entradas no expiran por defecto."""
        ...

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor del caché.
        
        Args:
            key: Clave a buscar
            
        Returns:
            Valor asociado o None si no existe/expiró
        """
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Almacena un valor en el caché.
        
        Args:
            key: Clave única
            value: Valor a almacenar
            ttl: Tiempo de vida en segundos.
                 - None: Usar default_ttl del backend
                 - 0 o negativo: No cachear (política del backend)
                 - Positivo: TTL específico
        """
        ...

    @abstractmethod
    def invalidate(self, key: str) -> bool:
        """
        Invalida una entrada específica.
        
        Args:
            key: Clave a invalidar
            
        Returns:
            True si existía y fue eliminada, False si no existía
        """
        ...

    @abstractmethod
    def cleanup(self) -> int:
        """
        Elimina entradas expiradas del caché.
        
        Este método es llamado periódicamente por cache_cleanup_job.
        
        Returns:
            Número de entradas eliminadas
        """
        ...

    @abstractmethod
    def get_stats(self) -> dict:
        """
        Retorna estadísticas del caché.
        
        Returns:
            Dict con métricas estandarizadas:
            - size: int - Entradas actuales
            - max_size: Optional[int] - Límite máximo
            - hits: int - Aciertos
            - misses: int - Fallos
            - evictions: int - Evictions por capacidad
            - invalidations: int - Eliminaciones explícitas
            - expired_removals: int - Eliminaciones por TTL
            - hit_rate_percent: float - Tasa de aciertos
            - total_requests: int - Total de requests
        """
        ...
