# -*- coding: utf-8 -*-
"""
backend/app/shared/enums/__init__.py

Export central consolidado de enums compartidos entre múltiples módulos.

Los enums específicos de auth y billing ahora están en sus módulos respectivos:
- Auth enums → backend/app/modules/auth/enums/
- Billing enums → backend/app/modules/billing/ (si se necesitan)

Este archivo solo exporta enums verdaderamente compartidos.

Autor: DoxAI
Fecha: 2025-10-23 (Reorganización modular)
"""

# ===== EMAIL =====
from .email_status_enum import EmailStatus, as_pg_enum as email_status_pg_enum
from .email_type_enum import EmailType, as_pg_enum as email_type_pg_enum

# ===== PROJECTS (DEPRECATED - Rompe principio de desacoplamiento) =====
# DEPRECATION WARNING: Este import crea dependencia inversa shared → modules.
# ProjectState debe importarse directamente desde backend.app.modules.projects.enums
# Este import se eliminará en diciembre 2025.
# 
# Razón: El paquete shared no debe depender de módulos de negocio para evitar
# ciclos de dependencia y mantener la arquitectura limpia.
try:
    from backend.app.modules.projects.enums.project_state_enum import ProjectState, as_pg_enum as project_state_pg_enum
except ImportError:
    # Si falla, no romper la importación de shared.enums
    ProjectState = None
    project_state_pg_enum = None


# ===== REGISTRY PARA ACCESO CENTRALIZADO =====
PG_ENUM_REGISTRY = {
    # Email
    "email_status_enum": email_status_pg_enum,
    "email_type_enum": email_type_pg_enum,
}

# Projects (legacy compatibility) - solo si se importó exitosamente
if project_state_pg_enum is not None:
    PG_ENUM_REGISTRY["project_state_enum"] = project_state_pg_enum


# ===== EXPORTS DINÁMICOS (EXCLUYE NONE) =====
__all__ = [
    # Email enums (siempre disponibles)
    "EmailStatus",
    "EmailType",
    # Email factories (para uso en modelos SQLAlchemy)
    "email_status_pg_enum",
    "email_type_pg_enum",
    # Registry central
    "PG_ENUM_REGISTRY",
]
# Fin del archivo