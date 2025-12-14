# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/compression_service.py

Servicio de compresión/descompresión para optimizar storage y transferencia.
Soporta múltiples algoritmos y detecta automáticamente cuando comprimir.

Autor: DoxAI
Fecha: 2025-11-05
"""

import gzip
import zlib
import brotli
from typing import Optional, Literal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

CompressionAlgo = Literal["gzip", "zlib", "brotli", "none"]


@dataclass
class CompressionResult:
    """Resultado de una operación de compresión."""
    data: bytes
    original_size: int
    compressed_size: int
    algorithm: CompressionAlgo
    ratio: float  # ratio de compresión (compressed/original)
    
    @property
    def savings_percent(self) -> float:
        """Retorna el porcentaje de ahorro."""
        if self.original_size == 0:
            return 0.0
        return (1 - self.ratio) * 100


class CompressionService:
    """
    Servicio para compresión/descompresión de archivos.
    """
    
    # Umbral mínimo de bytes para intentar compresión (archivos pequeños no se benefician)
    MIN_SIZE_FOR_COMPRESSION = 1024  # 1 KB
    
    # Umbral de ratio para considerar la compresión efectiva
    MIN_COMPRESSION_RATIO = 0.9  # Solo comprimir si reduce al menos 10%
    
    # Tipos MIME que típicamente se benefician de compresión
    COMPRESSIBLE_MIME_TYPES = {
        "text/plain",
        "text/html",
        "text/css",
        "text/javascript",
        "application/json",
        "application/xml",
        "text/xml",
        "application/javascript",
        "text/csv",
        "application/x-yaml",
    }
    
    # Tipos MIME que ya están comprimidos
    ALREADY_COMPRESSED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "audio/mpeg",
        "audio/ogg",
        "application/pdf",
        "application/zip",
        "application/gzip",
        "application/x-rar-compressed",
        "application/x-7z-compressed",
    }
    
    def should_compress(
        self,
        data: bytes,
        mime_type: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        """
        Determina si vale la pena comprimir los datos.
        
        Args:
            data: Datos a evaluar
            mime_type: Tipo MIME del archivo
            force: Forzar compresión sin importar heurísticas
            
        Returns:
            bool: True si se recomienda comprimir
        """
        if force:
            return True
            
        # Archivos muy pequeños no se benefician
        if len(data) < self.MIN_SIZE_FOR_COMPRESSION:
            return False
        
        # Verificar tipo MIME
        if mime_type:
            mime_lower = mime_type.lower()
            
            # No comprimir archivos ya comprimidos
            if mime_lower in self.ALREADY_COMPRESSED_MIME_TYPES:
                return False
            
            # Comprimir tipos de texto
            if mime_lower in self.COMPRESSIBLE_MIME_TYPES:
                return True
        
        # Por defecto, intentar comprimir archivos medianos/grandes
        return len(data) >= self.MIN_SIZE_FOR_COMPRESSION * 4  # >= 4 KB
    
    def compress(
        self,
        data: bytes,
        algorithm: CompressionAlgo = "gzip",
        level: int = 6,
    ) -> CompressionResult:
        """
        Comprime datos usando el algoritmo especificado.
        
        Args:
            data: Datos a comprimir
            algorithm: Algoritmo de compresión
            level: Nivel de compresión (1-9 para gzip/zlib, 0-11 para brotli)
            
        Returns:
            CompressionResult: Resultado con datos comprimidos y métricas
        """
        original_size = len(data)
        
        try:
            if algorithm == "gzip":
                compressed = gzip.compress(data, compresslevel=level)
            elif algorithm == "zlib":
                compressed = zlib.compress(data, level=level)
            elif algorithm == "brotli":
                # Brotli usa nivel 0-11, ajustar si viene de 1-9
                brotli_level = min(level, 11)
                compressed = brotli.compress(data, quality=brotli_level)
            elif algorithm == "none":
                compressed = data
            else:
                raise ValueError(f"Algoritmo desconocido: {algorithm}")
            
            compressed_size = len(compressed)
            ratio = compressed_size / original_size if original_size > 0 else 1.0
            
            result = CompressionResult(
                data=compressed,
                original_size=original_size,
                compressed_size=compressed_size,
                algorithm=algorithm,
                ratio=ratio,
            )
            
            if ratio < 1.0:
                logger.debug(
                    f"🗜️  Compressed {original_size} bytes → {compressed_size} bytes "
                    f"({result.savings_percent:.1f}% savings) using {algorithm}"
                )
            else:
                logger.debug(
                    f"🗜️  Compression not effective: {original_size} bytes → {compressed_size} bytes "
                    f"using {algorithm}, returning original"
                )
            
            return result
            
        except Exception as e:
            logger.warning(f"Compression failed with {algorithm}: {e}, returning original")
            return CompressionResult(
                data=data,
                original_size=original_size,
                compressed_size=original_size,
                algorithm="none",
                ratio=1.0,
            )
    
    def decompress(
        self,
        data: bytes,
        algorithm: CompressionAlgo,
    ) -> bytes:
        """
        Descomprime datos usando el algoritmo especificado.
        
        Args:
            data: Datos comprimidos
            algorithm: Algoritmo usado para comprimir
            
        Returns:
            bytes: Datos descomprimidos
        """
        try:
            if algorithm == "gzip":
                return gzip.decompress(data)
            elif algorithm == "zlib":
                return zlib.decompress(data)
            elif algorithm == "brotli":
                return brotli.decompress(data)
            elif algorithm == "none":
                return data
            else:
                raise ValueError(f"Algoritmo desconocido: {algorithm}")
                
        except Exception as e:
            logger.error(f"Decompression failed with {algorithm}: {e}")
            raise
    
    def smart_compress(
        self,
        data: bytes,
        mime_type: Optional[str] = None,
        preferred_algo: CompressionAlgo = "gzip",
    ) -> CompressionResult:
        """
        Comprime inteligentemente: solo si vale la pena y retorna el mejor resultado.
        
        Args:
            data: Datos a comprimir
            mime_type: Tipo MIME para heurística
            preferred_algo: Algoritmo preferido
            
        Returns:
            CompressionResult: Mejor resultado (puede ser sin compresión)
        """
        if not self.should_compress(data, mime_type):
            return CompressionResult(
                data=data,
                original_size=len(data),
                compressed_size=len(data),
                algorithm="none",
                ratio=1.0,
            )
        
        result = self.compress(data, algorithm=preferred_algo)
        
        # Solo usar compresión si reduce significativamente
        if result.ratio > self.MIN_COMPRESSION_RATIO:
            logger.debug(
                f"Compression not worthwhile (ratio={result.ratio:.2f}), keeping original"
            )
            return CompressionResult(
                data=data,
                original_size=len(data),
                compressed_size=len(data),
                algorithm="none",
                ratio=1.0,
            )
        
        return result


# Instancia global singleton
_compression_service: Optional[CompressionService] = None


def get_compression_service() -> CompressionService:
    """Obtiene la instancia singleton del servicio de compresión."""
    global _compression_service
    if _compression_service is None:
        _compression_service = CompressionService()
    return _compression_service


__all__ = [
    "CompressionService",
    "CompressionResult",
    "CompressionAlgo",
    "get_compression_service",
]
