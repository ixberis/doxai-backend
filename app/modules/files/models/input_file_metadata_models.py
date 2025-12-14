
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/input_file_metadata_models.py

Modelo de metadatos técnicos para archivos INSUMO.

Alineación con DB:
- Corresponde a la tabla `public.input_file_metadata`:
  database/files/02_tables/02_input_file_metadata.sql
- Relación 1:1 con `input_files` (ON DELETE CASCADE).

Campos:
- parser_version: versión del parser utilizado.
- checksum / checksum_algo: integridad del archivo insumo.
- extracted_at / processed_at: tiempos de OCR/parsing y posterior pipeline.
- error_message: detalle de error en caso de fallo.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.shared.database import Base
from app.modules.files.enums import (
    ChecksumAlgo,
    checksum_algo_as_pg_enum,
)

if TYPE_CHECKING:
    from app.modules.files.models.input_file_models import InputFile


class InputFileMetadata(Base):
    """
    Metadatos técnicos asociados a un archivo insumo.
    """
    __tablename__ = "input_file_metadata"

    input_file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "input_files.input_file_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    parser_version: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    checksum_algo: Mapped[Optional[ChecksumAlgo]] = mapped_column(
        checksum_algo_as_pg_enum(),
        nullable=True,
    )

    checksum: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    extracted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Synonyms para compatibilidad con nombres prefijados en tests/schemas
    input_file_hash_checksum = synonym("checksum")
    input_file_checksum_algo = synonym("checksum_algo")
    input_file_processed_at = synonym("processed_at")

    # Relación 1:1 hacia InputFile
    input_file: Mapped["InputFile"] = relationship(
        "InputFile",
        back_populates="metadata_entries",
        lazy="raise",
        uselist=False,
    )


__all__ = ["InputFileMetadata"]

# Fin del archivo backend/app/modules/files/models/input_file_metadata_models.py