# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/connection_pool.py

Pool de conexiones HTTP optimizado para operaciones de storage.
Mejora el rendimiento mediante:
- Reutilización de conexiones
- Límites configurables de conexiones
- Timeouts optimizados
- Keep-alive automático

Autor: DoxAI
Fecha: 2025-11-05
"""

import httpx
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Pool de conexiones HTTP singleton optimizado para Supabase Storage.
    """
    _instance: Optional["ConnectionPool"] = None
    _lock = asyncio.Lock()
    
    def __init__(
        self,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        keepalive_expiry: float = 30.0,
        timeout: float = 30.0,
    ):
        """
        Inicializa el pool de conexiones.
        
        Args:
            max_connections: Máximo de conexiones simultáneas
            max_keepalive_connections: Máximo de conexiones keep-alive
            keepalive_expiry: Tiempo de expiración de keep-alive en segundos
            timeout: Timeout general en segundos
        """
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def get_client(self) -> httpx.AsyncClient:
        """
        Obtiene o crea el cliente HTTP con pooling optimizado.
        
        Returns:
            httpx.AsyncClient: Cliente HTTP compartido
        """
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
                keepalive_expiry=self.keepalive_expiry,
            )
            
            timeout = httpx.Timeout(
                connect=self.timeout,
                read=self.timeout,
                write=self.timeout,
                pool=self.timeout,
            )
            
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                http2=True,  # Habilitar HTTP/2 para mejor performance
                follow_redirects=True,
            )
            
            logger.info(
                f"🔗 Connection pool initialized: "
                f"max_connections={self.max_connections}, "
                f"keepalive={self.max_keepalive_connections}"
            )
            
        return self._client
    
    async def close(self) -> None:
        """Cierra el pool de conexiones."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("🔒 Connection pool closed")
    
    @classmethod
    async def get_instance(cls) -> "ConnectionPool":
        """
        Obtiene la instancia singleton del pool.
        
        Returns:
            ConnectionPool: Instancia única del pool
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance


# Función helper para obtener cliente del pool
async def get_pooled_client() -> httpx.AsyncClient:
    """
    Obtiene un cliente HTTP del pool de conexiones.
    
    Returns:
        httpx.AsyncClient: Cliente HTTP con pooling
    """
    pool = await ConnectionPool.get_instance()
    return await pool.get_client()


# Función helper para cerrar el pool
async def close_connection_pool() -> None:
    """Cierra el pool de conexiones global."""
    if ConnectionPool._instance:
        await ConnectionPool._instance.close()
        ConnectionPool._instance = None


__all__ = ["ConnectionPool", "get_pooled_client", "close_connection_pool"]
