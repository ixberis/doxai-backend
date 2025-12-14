
# -*- coding: utf-8 -*-
"""
backend/app/utils/project_state_utils.py

Utilidad para gestionar la progresión de estados en un proyecto DoxAI.

Implementa una lógica de máquina de estados finitos (FSM) lineal:
- Cada estado solo puede avanzar al siguiente en orden.
- No se permiten regresos ni saltos entre estados.

Autor: Ixchel Beristain
Fecha: 2025-10-23
"""

from app.modules.projects.enums.project_state_enum import ProjectState
from typing import Optional


STATE_SEQUENCE = [
    ProjectState.created,
    ProjectState.uploading,
    ProjectState.processing,
    ProjectState.ready,
    ProjectState.error,
    ProjectState.archived,
]

def get_next_state(current_state: ProjectState) -> Optional[ProjectState]:
    """
    Devuelve el siguiente estado en la secuencia del proyecto.

    Args:
        current_state (ProjectState): Estado actual del proyecto.

    Returns:
        ProjectState | None: Siguiente estado si existe, o None si es la última o inválida.
    """
    try:
        idx = STATE_SEQUENCE.index(current_state)
        return STATE_SEQUENCE[idx + 1]
    except (ValueError, IndexError):
        return None


def is_valid_transition(current: ProjectState, proposed: ProjectState) -> bool:
    """
    Verifica si una transición entre estados es válida según la secuencia lineal.

    Args:
        current (ProjectState): Estado actual.
        proposed (ProjectState): Estado propuesto.

    Returns:
        bool: True si la transición es válida (es el siguiente estado), False en caso contrario.
    """
    return get_next_state(current) == proposed
# Fin del código
