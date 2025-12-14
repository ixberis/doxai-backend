# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/checksum_algo_enum.py

Enum de algoritmos de checksum/hash para archivos en DoxAI.
Para verificación de integridad y firma de archivos.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-25
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class ChecksumAlgo(EnumMixin, _StrEnum):
    """
    Algoritmo de checksum/hash para verificación de integridad.
    
    El algoritmo operativo por defecto en DoxAI es SHA-256,
    que ofrece un balance óptimo entre seguridad y rendimiento.
    
    Valores:
        sha256: SHA-256 (default operativo, recomendado)
        md5: MD5 (legacy, menos seguro pero más rápido)
        sha1: SHA-1 (intermedio)
        sha512: SHA-512 (máxima seguridad, más lento)
    """
    sha256 = "sha256"
    md5 = "md5"
    sha1 = "sha1"
    sha512 = "sha512"
    
    # Aliases legacy
    SHA256 = sha256
    MD5 = md5
    SHA1 = sha1
    SHA512 = sha512


def as_pg_enum(name: str = "checksum_algo_enum", native_enum: bool = False) -> PG_ENUM:
    """
    Devuelve un Enum de SQLAlchemy ligado a ChecksumAlgo.
    """
    return PG_ENUM(
        ChecksumAlgo,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x]
    )


__all__ = ["ChecksumAlgo", "as_pg_enum"]
