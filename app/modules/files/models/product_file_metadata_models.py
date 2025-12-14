
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/product_file_metadata_models.py

Modelo de metadatos enriquecidos para archivos PRODUCTO.

Alineación con DB:
- Corresponde a la tabla `public.product_file_metadata`:
  database/files/02_tables/04_product_file_metadata.sql
- Relación 1:1 con `product_files` (ON DELETE CASCADE).

Incluye:
- generation_method + generation_params + ragmodel_version_used.
- page_count, word_count.
- keywords, entities, sections, summary.
- checksum / checksum_algo, extracted_at.
- approved_by / approved_at / review_notes.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from sqlalchemy.ext.hybrid import hybrid_property

from app.shared.database import Base
from app.modules.files.enums import (
    GenerationMethod,
    ChecksumAlgo,
    ProductVersion,
    generation_method_as_pg_enum,
    checksum_algo_as_pg_enum,
    product_version_as_pg_enum,
)

if TYPE_CHECKING:
    from app.modules.files.models.product_file_models import ProductFile


class ProductFileMetadata(Base):
    """
    Metadatos enriquecidos del archivo producto.
    
    NOTA: Los nombres de columna en SQL son cortos (checksum, generation_method, etc.)
    pero se aceptan aliases con prefijo product_file_* para compatibilidad con tests y schemas.
    """
    __tablename__ = "product_file_metadata"

    def __init__(self, **kwargs):
        """
        Inicialización personalizada para aceptar aliases con prefijo product_file_*.
        
        NOTA: Los synonyms ya manejan la mayoría del mapeo automáticamente.
        Solo necesitamos procesar product_file_is_approved.
        """
        # Procesar product_file_is_approved y mapearlo a is_approved
        if "product_file_is_approved" in kwargs:
            kwargs["is_approved"] = bool(kwargs.pop("product_file_is_approved"))
        
        super().__init__(**kwargs)

    product_file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "product_files.product_file_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    generation_method: Mapped[GenerationMethod] = mapped_column(
        generation_method_as_pg_enum(),
        nullable=False,
    )

    generation_params: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    ragmodel_version_used: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    word_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    keywords: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    entities: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    sections: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    summary: Mapped[Optional[str]] = mapped_column(
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

    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    approved_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ========== Synonyms para hacer aliases consultables en SQL ==========
    # Estos permiten tanto construcción como queries con nombres prefijados
    product_file_hash_checksum = synonym("checksum")
    product_file_checksum_algo = synonym("checksum_algo")
    product_file_generation_method = synonym("generation_method")
    product_file_extracted_at = synonym("extracted_at")
    product_file_ragmodel_version_used = synonym("ragmodel_version_used")

    # Relación 1:1 hacia ProductFile
    product_file: Mapped["ProductFile"] = relationship(
        "ProductFile",
        back_populates="metadata_entries",
        lazy="raise",
        uselist=False,
    )

    # ========== Properties computed (no consultables, solo read) ==========

    @property
    def product_file_version_used(self) -> Optional[str]:
        """Alias legacy de ragmodel_version_used para compatibilidad con ProductVersion enum."""
        return self.ragmodel_version_used

    @product_file_version_used.setter
    def product_file_version_used(self, value):
        """Acepta ProductVersion enum o str."""
        if hasattr(value, 'value'):
            self.ragmodel_version_used = value.value
        else:
            self.ragmodel_version_used = str(value) if value else None

    @hybrid_property
    def product_file_is_approved(self) -> bool:
        """
        Hybrid property consultable en SQL sobre la columna is_approved.
        
        Los tests pueden pasar este campo en constructor y también
        usarlo en queries SQL.
        """
        return self.is_approved

    @product_file_is_approved.setter
    def product_file_is_approved(self, value: bool):
        """Setter para permitir asignación directa."""
        self.is_approved = bool(value)

    @product_file_is_approved.expression
    def product_file_is_approved(cls):
        """Expresión SQL para product_file_is_approved."""
        return cls.is_approved


__all__ = ["ProductFileMetadata"]

# Fin del archivo backend/app/modules/files/models/product_file_metadata_models.py








