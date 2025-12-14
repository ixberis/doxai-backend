# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/checksum_utils.py

Utilidades para cálculo de checksums y verificación de integridad.

Autor: DoxAI
Fecha: 2025-10-28
"""

import hashlib
from typing import BinaryIO


def calculate_sha256(data: bytes) -> str:
    """
    Calcula checksum SHA-256 de datos binarios.
    
    Args:
        data: Datos binarios
        
    Returns:
        Checksum en formato hexadecimal
    """
    return hashlib.sha256(data).hexdigest()


def calculate_sha256_file(file_path: str, chunk_size: int = 8192) -> str:
    """
    Calcula checksum SHA-256 de un archivo.
    
    Args:
        file_path: Ruta del archivo
        chunk_size: Tamaño del buffer de lectura
        
    Returns:
        Checksum en formato hexadecimal
    """
    sha256 = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def calculate_md5(data: bytes) -> str:
    """
    Calcula checksum MD5 de datos binarios.
    
    Args:
        data: Datos binarios
        
    Returns:
        Checksum en formato hexadecimal
        
    Note:
        MD5 no es seguro criptográficamente, pero útil para 
        detección rápida de duplicados/cambios.
    """
    return hashlib.md5(data).hexdigest()


def verify_checksum(data: bytes, expected_checksum: str, algorithm: str = "sha256") -> bool:
    """
    Verifica checksum de datos contra valor esperado.
    
    Args:
        data: Datos binarios
        expected_checksum: Checksum esperado
        algorithm: Algoritmo ("sha256" o "md5")
        
    Returns:
        True si coincide, False si no
    """
    if algorithm == "sha256":
        actual = calculate_sha256(data)
    elif algorithm == "md5":
        actual = calculate_md5(data)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    return actual.lower() == expected_checksum.lower()
