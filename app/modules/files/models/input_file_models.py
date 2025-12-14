
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/input_file_models.py

Modelo que representa archivos INSUMO de un proyecto.

Alineación con DB:
- Corresponde a la tabla `public.input_files` definida en:
  database/files/02_tables/01_input_files.sql
  y sus FKs en 06_foreign_keys_files.sql y 09_add_file_id_to_input_product_files.sql.
- El pipeline de procesamiento vive en `input_file_status` (uploaded → ...).
- Los nombres y tipos siguen el contrato de SQL (citext, enums, tamaños).

Decisión de diseño Files v2:
- Se mantiene `input_file_id` como PK de la tabla (no se toca el DDL).
- Se agrega/usa `file_id` como FK único a `files_base.file_id` para integración
  canónica con otros módulos y con la tabla `files_base`.

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
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.files.enums import (
    FileType,
    FileCategory,
    FileLanguage,
    InputFileClass,
    IngestSource,
    StorageBackend,
    InputProcessingStatus,
    file_type_as_pg_enum,
    file_category_as_pg_enum,
    file_language_as_pg_enum,
    input_file_class_as_pg_enum,
    ingest_source_as_pg_enum,
    storage_backend_as_pg_enum,
    input_processing_status_as_pg_enum,
)

if TYPE_CHECKING:
    from app.modules.projects.models.project_models import Project
    from app.modules.files.models.input_file_metadata_models import InputFileMetadata
    from app.modules.files.models.files_base_models import FilesBase


class InputFile(Base):
    """
    Archivo INSUMO asociado a un proyecto.

    - Representa un archivo subido por la persona usuaria.
    - Se usa como fuente para RAG u otros módulos de procesamiento.
    """
    __tablename__ = "input_files"

    # PK local
    input_file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # FK opcional hacia files_base.file_id (rellenado por script 09_add_file_id...)
    file_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files_base.file_id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )

    # Proyecto y usuario que sube
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_file_uploaded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    # Nombres y tipo físico
    # Nota: La BD usa citext para case-insensitivity, pero el ORM usa Text
    # ya que PostgreSQL maneja la comparación case-insensitive a nivel de tipo de columna.
    input_file_original_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    input_file_display_name: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    input_file_mime_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    input_file_extension: Mapped[Optional[str]] = mapped_column(
        String(length=32),
        nullable=True,
    )

    # Tamaño y clasificación lógica
    input_file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    input_file_type: Mapped[FileType] = mapped_column(
        file_type_as_pg_enum(),
        nullable=False,
    )

    # En SQL existe la columna input_file_category, pero su valor lógico es
    # siempre "input" para esta tabla; se modela como Enum para reflejar el DDL.
    input_file_category: Mapped[FileCategory] = mapped_column(
        file_category_as_pg_enum(),
        nullable=False,
        server_default=FileCategory.input.value,
    )

    input_file_class: Mapped[InputFileClass] = mapped_column(
        input_file_class_as_pg_enum(),
        nullable=False,
        server_default=InputFileClass.source.value,
    )

    input_file_language: Mapped[Optional[FileLanguage]] = mapped_column(
        file_language_as_pg_enum(),
        nullable=True,
    )

    # Origen y almacenamiento
    input_file_ingest_source: Mapped[IngestSource] = mapped_column(
        ingest_source_as_pg_enum(),
        nullable=False,
        server_default=IngestSource.upload.value,
    )

    input_file_storage_backend: Mapped[StorageBackend] = mapped_column(
        storage_backend_as_pg_enum(),
        nullable=False,
        server_default=StorageBackend.supabase.value,
    )

    input_file_storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Estado del pipeline
    input_file_status: Mapped[InputProcessingStatus] = mapped_column(
        input_processing_status_as_pg_enum(),
        nullable=False,
        server_default=InputProcessingStatus.uploaded.value,
    )

    # Flags y timestamp
    input_file_is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    input_file_is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    input_file_uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    project: Mapped["Project"] = relationship("Project", lazy="raise")
    metadata_entries: Mapped[Optional["InputFileMetadata"]] = relationship(
        "InputFileMetadata",
        back_populates="input_file",
        lazy="raise",
        uselist=False,
    )
    # Relación MANY-TO-ONE con FilesBase usando InputFile.file_id -> FilesBase.file_id
    files_base: Mapped[Optional["FilesBase"]] = relationship(
        "FilesBase",
        back_populates="input_file",
        foreign_keys=[file_id],
        lazy="raise",
        uselist=False,
        overlaps="input_file",
    )

    __table_args__ = (
        CheckConstraint(
            "input_file_size_bytes >= 0",
            name="ck_input_files_size_nonnegative",
        ),
        CheckConstraint(
            "length(input_file_storage_path) > 0",
            name="ck_input_files_storage_path_not_empty",
        ),
        UniqueConstraint(
            "project_id",
            "input_file_storage_path",
            name="uq_input_files_project_path",
        ),
    )


# Event listener para autocomplete de original_name con display_name
@event.listens_for(InputFile, "before_insert")
def _set_original_name_default(mapper, connection, target):
    """
    Autocomplete input_file_original_name con input_file_display_name si no se proporciona.
    
    Esto permite que los tests y código que solo especifican display_name funcionen
    correctamente sin violar la constraint NOT NULL de input_file_original_name.
    """
    if target.input_file_original_name is None or target.input_file_original_name == "":
        target.input_file_original_name = target.input_file_display_name or ""


__all__ = ["InputFile"]

# Fin del archivo backend/app/modules/files/models/input_file_models.py





