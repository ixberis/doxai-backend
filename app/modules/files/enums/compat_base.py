# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/compat_base.py

Base compatible para enums string en DoxAI.
Evita conflictos de MRO al proveer una única clase base StrEnum
que funciona tanto en Python 3.11+ como en versiones anteriores.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations
from typing import Any, TypeVar, List, Optional

try:
    # Python 3.11+ tiene StrEnum nativo
    from enum import StrEnum as _StrEnum
except ImportError:  # pragma: no cover
    # Para Python < 3.11, creamos una clase compatible
    from enum import Enum as _Enum
    
    class _StrEnum(str, _Enum):
        """StrEnum compatible con Python < 3.11"""
        pass


T = TypeVar('T', bound='EnumMixin')


class EnumMixin:
    """
    Mixin para enums con métodos helper de validación y conversión.
    Usar junto con _StrEnum para todos los enums del módulo.
    """
    
    @classmethod
    def values(cls) -> List[str]:
        """
        Devuelve lista de todos los valores del enum (sin aliases).
        Útil para validaciones y documentación.
        """
        seen = set()
        result = []
        for member in cls:  # type: ignore
            if member.value not in seen:
                seen.add(member.value)
                result.append(member.value)
        return result
    
    def label(self) -> str:
        """Nombre legible por humanos; por omisión el value."""
        return str(getattr(self, "value", self))
    
    def to_json(self) -> str:
        """Serialización explícita para JSON; devuelve el valor del enum."""
        return str(getattr(self, "value", self))
    
    def __str__(self) -> str:  # type: ignore[override]
        """Representación por defecto; devuelve el valor del enum."""
        return str(getattr(self, "value", self))
    
    @classmethod
    def from_any(cls: type[T], value: Any) -> T:
        """
        Convierte 'value' al enum:
        - Acepta ya-miembro del enum
        - Acepta nombre de miembro (case-insensitive), incluyendo aliases
        - Acepta valor de miembro (normalizado con casefold)
        
        Args:
            value: Valor a convertir (str, enum member, nombre de miembro, etc)
            
        Returns:
            Miembro del enum correspondiente
            
        Raises:
            ValueError: Si el valor no es válido para este enum
        """
        if isinstance(value, cls):
            return value  # type: ignore

        if isinstance(value, str):
            s = value.strip()

            # Optimización: crear mapas para evitar múltiples recorridos
            members = cls.__members__.copy()
            name_map = {k.casefold(): v for k, v in members.items()}
            value_map = {str(getattr(m, "value", "")).casefold(): m for m in cls}  # type: ignore

            # 1) Buscar por nombre (case-insensitive con casefold)
            s_folded = s.casefold()
            if s_folded in name_map:
                return name_map[s_folded]  # type: ignore

            # 2) Buscar por valor normalizado (casefold)
            if s_folded in value_map:
                return value_map[s_folded]  # type: ignore

            # 3) Intento final: constructor por valor exacto (por si no es str)
            try:
                return cls(s)  # type: ignore
            except Exception:
                pass

        raise ValueError(f"{value!r} no es válido para {cls.__name__}")
    
    @classmethod
    def get(cls: type[T], value: Any, default: Optional[T] = None) -> Optional[T]:
        """
        Wrapper de from_any() con default para evitar excepciones.
        Útil cuando parseas inputs de cliente y no quieres excepciones.
        
        IMPORTANTE: Este método NO valida; devuelve default silenciosamente
        si el valor no es válido. Para validación estricta, usa from_any().
        
        Args:
            value: Valor a convertir
            default: Valor por defecto si la conversión falla (default: None)
            
        Returns:
            Miembro del enum o default si la conversión falla
        """
        try:
            return cls.from_any(value)
        except ValueError:
            return default


__all__ = ["_StrEnum", "EnumMixin"]
