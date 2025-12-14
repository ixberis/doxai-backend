# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/file_checksum_service.py

Servicios utilitarios para cálculo y verificación de checksums de archivos.
"""

from __future__ import annotations

import hashlib
from typing import BinaryIO, Union

from app.modules.files.enums import ChecksumAlgo


def _get_hash_instance(algo: Union[ChecksumAlgo, str]) -> "hashlib._Hash":
    """Devuelve una instancia de hashlib para el algoritmo especificado."""
    algo_str = algo.value if isinstance(algo, ChecksumAlgo) else str(algo).lower()
    
    if algo_str == "md5":
        return hashlib.md5()
    if algo_str == "sha1":
        return hashlib.sha1()
    if algo_str == "sha256":
        return hashlib.sha256()
    if algo_str == "sha512":
        return hashlib.sha512()

    raise ValueError(f"Algoritmo de checksum no soportado: {algo_str}")


def compute_checksum_bytes(data: bytes, algo: Union[ChecksumAlgo, str]) -> str:
    """Calcula el checksum de un bloque de bytes completo."""
    h = _get_hash_instance(algo)
    h.update(data)
    return h.hexdigest()


def compute_checksum_stream(
    stream: BinaryIO,
    algo: Union[ChecksumAlgo, str],
    chunk_size: int = 8192,
) -> str:
    """
    Calcula el checksum de un stream file-like leyéndolo por chunks.
    
    Args:
        stream: Objeto con interface de archivo (readable)
        algo: Algoritmo de hash a usar
        chunk_size: Tamaño de los bloques de lectura en bytes
        
    Returns:
        Hex digest del checksum
    """
    h = _get_hash_instance(algo)

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)

    return h.hexdigest()


def compute_checksum(
    data: Union[bytes, BinaryIO],
    algo: Union[ChecksumAlgo, str],
) -> str:
    """
    Calcula el checksum de bytes o un stream.
    
    Args:
        data: Bytes o stream file-like
        algo: Algoritmo de hash
        
    Returns:
        Hex digest del checksum
    """
    if isinstance(data, bytes):
        return compute_checksum_bytes(data, algo)
    else:
        return compute_checksum_stream(data, algo)


def verify_checksum(
    data: Union[bytes, BinaryIO],
    expected_hex: str,
    algo: Union[ChecksumAlgo, str],
) -> bool:
    """
    Verifica que el checksum de los datos coincida con el esperado.
    
    Args:
        data: Bytes o stream file-like
        expected_hex: Checksum esperado en formato hexadecimal
        algo: Algoritmo de hash
        
    Returns:
        True si coincide, False si no
    """
    # Reset stream position if it's a stream
    if hasattr(data, "seek"):
        data.seek(0)
    
    calculated = compute_checksum(data, algo)
    return calculated.lower() == expected_hex.lower()


__all__ = [
    "compute_checksum",
    "compute_checksum_bytes",
    "compute_checksum_stream",
    "verify_checksum",
]
