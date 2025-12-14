# app/shared/config/__init__.py
"""
Entry-point ligero para configuración.

Expone un único import estable:
    from app.shared.config import get_settings

No inicializa settings en import-time para evitar efectos colaterales
durante la recolección de tests.
"""

from app.shared.config.config_loader import get_settings

__all__ = ["get_settings"]
# fin del archivo