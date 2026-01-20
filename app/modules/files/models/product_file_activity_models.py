
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/product_file_activity_models.py

Bitácora de actividad sobre archivos PRODUCTO (auditoría).

Alineación con DB:
- Corresponde a la tabla `public.product_file_activity`:
  database/files/02_tables/05_product_file_activity.sql
  y a sus FKs en 06_foreign_keys_files.sql.
- Registra eventos sobre archivos producto: descargas, vistas, regeneraciones, etc.

Campos clave:
- event_type: ProductFileEvent (enum).
- snapshot_*: snapshot desnormalizado del artefacto en el momento del evento.
- details: jsonb con payload adicional.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Text,
    Integer,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.files.enums import (
    ProductFileEvent,
    product_file_event_as_pg_enum,
)

if TYPE_CHECKING:
    from app.modules.projects.models.project_models import Project
    from app.modules.files.models.product_file_models import ProductFile


class ProductFileActivity(Base):
    """
    Evento de actividad sobre un archivo producto.
    """
    __tablename__ = "product_file_activity"

    product_file_activity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    def __init__(self, **kwargs):
        """Inicialización personalizada para aceptar aliases de campos snapshot_*."""
        # Mapear aliases a nombres reales de columnas
        if "product_file_display_name" in kwargs:
            kwargs["snapshot_name"] = kwargs.pop("product_file_display_name")
        if "product_file_storage_path" in kwargs:
            kwargs["snapshot_path"] = kwargs.pop("product_file_storage_path")
        if "product_file_mime_type" in kwargs:
            kwargs["snapshot_mime_type"] = kwargs.pop("product_file_mime_type")
        if "product_file_size_bytes" in kwargs:
            kwargs["snapshot_size_bytes"] = kwargs.pop("product_file_size_bytes")
        
        super().__init__(**kwargs)

    # SSOT: auth_user_id es el dueño del evento (JWT.sub)
    auth_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_file_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("product_files.product_file_id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[ProductFileEvent] = mapped_column(
        product_file_event_as_pg_enum(),
        nullable=False,
    )

    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    # Snapshot desnormalizado del artefacto al momento del evento
    snapshot_name: Mapped[Optional[str]] = mapped_column(
        "snapshot_name",
        Text,
        nullable=True,
    )
    snapshot_path: Mapped[Optional[str]] = mapped_column(
        "snapshot_path",
        Text,
        nullable=True,
    )
    snapshot_mime_type: Mapped[Optional[str]] = mapped_column(
        "snapshot_mime_type",
        Text,
        nullable=True,
    )
    snapshot_size_bytes: Mapped[Optional[int]] = mapped_column(
        "snapshot_size_bytes",
        Integer,
        nullable=True,
    )

    details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Aliases para compatibilidad con tests y código legacy
    @property
    def product_file_display_name(self) -> Optional[str]:
        """Alias de snapshot_name."""
        return self.snapshot_name

    @product_file_display_name.setter
    def product_file_display_name(self, value: Optional[str]):
        self.snapshot_name = value

    @property
    def product_file_storage_path(self) -> Optional[str]:
        """Alias de snapshot_path."""
        return self.snapshot_path

    @product_file_storage_path.setter
    def product_file_storage_path(self, value: Optional[str]):
        self.snapshot_path = value

    @property
    def product_file_mime_type(self) -> Optional[str]:
        """Alias de snapshot_mime_type."""
        return self.snapshot_mime_type

    @product_file_mime_type.setter
    def product_file_mime_type(self, value: Optional[str]):
        self.snapshot_mime_type = value

    @property
    def product_file_size_bytes(self) -> Optional[int]:
        """Alias de snapshot_size_bytes."""
        return self.snapshot_size_bytes

    @product_file_size_bytes.setter
    def product_file_size_bytes(self, value: Optional[int]):
        self.snapshot_size_bytes = value

    # Relaciones
    project: Mapped["Project"] = relationship("Project", lazy="raise")
    product_file: Mapped[Optional["ProductFile"]] = relationship(
        "ProductFile",
        back_populates="activity_records",
        lazy="raise",
    )


__all__ = ["ProductFileActivity"]

# Fin del archivo backend/app/modules/files/models/product_file_activity_models.py






