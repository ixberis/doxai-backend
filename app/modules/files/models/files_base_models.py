
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/files_base_models.py

Modelo base canónico para archivos de proyecto (insumo y producto).

Alineación con DB:
- Corresponde a la tabla `public.files_base` definida en:
  database/files/02_tables/07_files_base.sql
  y sus FKs en 08_files_base_foreign_keys.sql.
- Cada fila representa un archivo lógico asociado a un proyecto.
- Se vincula de forma exclusiva a `input_files` O `product_files`:
  - logical_role = 'input'   ⇒ input_file_id NOT NULL, product_file_id NULL
  - logical_role = 'product' ⇒ product_file_id NOT NULL, input_file_id NULL

Uso:
- Identificador canónico `file_id` para integración inter-módulos (Projects, RAG, Admin).
- Punto de anclaje para futuras extensiones (tags, ownership avanzado, etc.).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.files.enums.file_role_enum import FileRole, file_role_as_pg_enum

if TYPE_CHECKING:
    # Imports sólo para tipado (Pylance / mypy), no se ejecutan en runtime
    from app.modules.projects.models.project_models import Project
    from app.modules.files.models.input_file_models import InputFile
    from app.modules.files.models.product_file_models import ProductFile


class FilesBase(Base):
    """
    Tabla base canónica para cualquier archivo de proyecto (input/product).

    NOTA IMPORTANTE:
    - `file_id` es la PK global de archivos.
    - `input_file_id` y `product_file_id` siguen siendo PK locales en sus
      respectivas tablas (`input_files`, `product_files`).
    """
    __tablename__ = "files_base"

    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Ownership canónico (JWT.sub)
    auth_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    logical_role: Mapped[FileRole] = mapped_column(
        file_role_as_pg_enum(),
        nullable=False,
    )

    # Vinculación 1:1 con input_files / product_files
    # use_alter=True rompe el ciclo de dependencias para permitir DROP ordenado
    input_file_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("input_files.input_file_id", ondelete="CASCADE", use_alter=True, name="fk_files_base_input_file_id"),
        unique=True,
        nullable=True,
    )

    product_file_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("product_files.product_file_id", ondelete="CASCADE", use_alter=True, name="fk_files_base_product_file_id"),
        unique=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relaciones (tipadas vía TYPE_CHECKING)
    project: Mapped["Project"] = relationship("Project", lazy="raise")
    
    # Relación inversa 1:1 con InputFile basada en InputFile.file_id -> FilesBase.file_id
    input_file: Mapped[Optional["InputFile"]] = relationship(
        "InputFile",
        back_populates="files_base",
        foreign_keys="[InputFile.file_id]",
        lazy="raise",
        uselist=False,
        overlaps="files_base",
    )
    
    # Relación inversa 1:1 con ProductFile basada en ProductFile.file_id -> FilesBase.file_id
    product_file: Mapped[Optional["ProductFile"]] = relationship(
        "ProductFile",
        back_populates="files_base",
        foreign_keys="[ProductFile.file_id]",
        lazy="raise",
        uselist=False,
        overlaps="files_base",
    )

    __table_args__ = (
        CheckConstraint(
            "(logical_role = 'input' AND input_file_id IS NOT NULL "
            "AND product_file_id IS NULL) "
            "OR (logical_role = 'product' AND product_file_id IS NOT NULL "
            "AND input_file_id IS NULL)",
            name="files_base_role_exclusive_chk",
        ),
    )


__all__ = ["FilesBase"]

# Fin del archivo backend/app/modules/files/models/files_base_models.py
