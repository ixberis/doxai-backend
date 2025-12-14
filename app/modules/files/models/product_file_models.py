
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/product_file_models.py

Modelo que representa archivos PRODUCTO generados por DoxAI.

Alineación con DB:
- Corresponde a la tabla `public.product_files`:
  database/files/02_tables/03_product_files.sql
  y a las FKs de 06_foreign_keys_files.sql y 09_add_file_id_to_input_product_files.sql.
- Incluye tipo lógico del archivo (ProductFileType), versión (ProductVersion) y
  metadatos básicos de almacenamiento.

Decisión de diseño Files v2:
- Se mantiene `product_file_id` como PK de la tabla.
- `file_id` referencia a `files_base.file_id` para unificar identificadores
  de archivos (insumo/producto) a nivel plataforma.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    Integer,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.files.enums import (
    FileLanguage,
    ProductFileType,
    ProductVersion,
    StorageBackend,
    file_language_as_pg_enum,
    product_file_type_as_pg_enum,
    product_version_as_pg_enum,
    storage_backend_as_pg_enum,
)

if TYPE_CHECKING:
    from app.modules.projects.models.project_models import Project
    from app.modules.files.models.product_file_metadata_models import ProductFileMetadata
    from app.modules.files.models.files_base_models import FilesBase
    from app.modules.files.models.product_file_activity_models import ProductFileActivity


class ProductFile(Base):
    """
    Archivo PRODUCTO generado por DoxAI.

    - Puede representar reportes, exports, artefactos RAG, etc.
    """
    __tablename__ = "product_files"

    # PK local
    product_file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # FK opcional hacia files_base.file_id
    file_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files_base.file_id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Nombres y tipo físico
    product_file_original_name: Mapped[str] = mapped_column(
        CITEXT,
        nullable=False,
    )
    product_file_display_name: Mapped[Optional[str]] = mapped_column(
        CITEXT,
        nullable=True,
    )
    product_file_mime_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    product_file_extension: Mapped[Optional[str]] = mapped_column(
        String(length=32),
        nullable=True,
    )

    product_file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Tipo lógico y contexto
    product_file_type: Mapped[ProductFileType] = mapped_column(
        product_file_type_as_pg_enum(),
        nullable=False,
    )

    product_file_version: Mapped[ProductVersion] = mapped_column(
        product_version_as_pg_enum(),
        nullable=False,
        server_default=ProductVersion.v1.value,
    )

    product_file_language: Mapped[Optional[FileLanguage]] = mapped_column(
        file_language_as_pg_enum(),
        nullable=True,
    )

    # Almacenamiento
    product_file_storage_backend: Mapped[StorageBackend] = mapped_column(
        storage_backend_as_pg_enum(),
        nullable=False,
        server_default=StorageBackend.supabase.value,
    )

    product_file_storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Auditoría
    product_file_generated_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    product_file_is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    product_file_is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    product_file_generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    project: Mapped["Project"] = relationship("Project", lazy="raise")
    metadata_entries: Mapped[Optional["ProductFileMetadata"]] = relationship(
        "ProductFileMetadata",
        back_populates="product_file",
        lazy="raise",
        uselist=False,
    )
    # Relación MANY-TO-ONE con FilesBase usando ProductFile.file_id -> FilesBase.file_id
    files_base: Mapped[Optional["FilesBase"]] = relationship(
        "FilesBase",
        back_populates="product_file",
        foreign_keys=[file_id],
        lazy="raise",
        uselist=False,
        overlaps="product_file",
    )
    activity_records: Mapped[list["ProductFileActivity"]] = relationship(
        "ProductFileActivity",
        back_populates="product_file",
        lazy="raise",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "product_file_size_bytes >= 0",
            name="ck_product_files_size_nonnegative",
        ),
        CheckConstraint(
            "length(product_file_storage_path) > 0",
            name="ck_product_files_storage_path_not_empty",
        ),
        UniqueConstraint(
            "project_id",
            "product_file_storage_path",
            name="uq_product_files_project_path",
        ),
    )


__all__ = ["ProductFile"]

# Fin del archivo backend/app/modules/files/models/product_file_models.py








