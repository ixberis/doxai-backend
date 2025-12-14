
# -*- coding: utf-8 -*-
"""
backend/app/utils/base_models.py

Modelo base personalizado para Pydantic en el backend de DoxAI.

Incluye:
- Eliminación automática de espacios en campos de texto (`str_strip_whitespace = True`)
- Modo de atributos activado para compatibilidad con ORM (`from_attributes = True`)
- Configuración optimizada para Pydantic v2
- Reexportación de utilidades comunes: `EmailStr` y `Field`

Este modelo debe usarse como base para todos los esquemas Pydantic compartidos por la API.

Autor: Ixchel Beristain
Fecha: 31/05/2025
Actualizado: 11/07/2025 - Migración a Pydantic v2
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UTF8SafeModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,             # reemplaza a orm_mode=True
        populate_by_name=True,            # para que funcionen los aliases
        str_strip_whitespace=True,        # elimina espacios de strings
        # json_encoders removido - deprecado en Pydantic v2
        # El manejo UTF-8 ahora es nativo en Pydantic v2
    )

__all__ = ["UTF8SafeModel", "EmailStr", "Field"]
# Fin del archivo base_models.py







