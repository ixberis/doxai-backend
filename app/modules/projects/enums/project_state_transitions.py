
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/project_state_transitions.py

Mapa de transiciones válidas para ProjectState.
Útil para validaciones de dominio y lógica de negocio.

Reglas de transición:
- created    → uploading          (inicio de carga de archivos)
- uploading  → processing | error (finaliza carga, inicia procesamiento o error)
- processing → ready | error      (procesamiento exitoso o error)
- ready      → processing | archived (reprocesamiento o archivado)
- error      → uploading | processing (reintentar desde carga o procesamiento)
- archived   → (estado terminal, sin transiciones)

Autor: Ixchel Beristáin
Fecha: 2025-10-28
"""

from typing import Dict, Set

from .project_state_enum import ProjectState


# Mapa de transiciones válidas: estado_origen → {estados_destino_permitidos}
VALID_STATE_TRANSITIONS: Dict[ProjectState, Set[ProjectState]] = {
    ProjectState.created: {
        ProjectState.uploading,
    },
    ProjectState.uploading: {
        ProjectState.processing,
        ProjectState.error,
    },
    ProjectState.processing: {
        ProjectState.ready,
        ProjectState.error,
    },
    ProjectState.ready: {
        ProjectState.processing,  # Permite reprocesamiento
        ProjectState.archived,
    },
    ProjectState.error: {
        ProjectState.uploading,   # Reintentar desde carga
        ProjectState.processing,  # Reintentar desde procesamiento
    },
    ProjectState.archived: set(),  # Estado terminal, sin transiciones
}

# 🔁 Backwards-compat:
# Mantener compatibilidad con código/tests que esperan `ProjectStateTransitions`
ProjectStateTransitions = VALID_STATE_TRANSITIONS


def is_valid_state_transition(
    from_state: ProjectState,
    to_state: ProjectState,
) -> bool:
    """
    Valida si una transición de estado es permitida.

    Args:
        from_state: Estado actual.
        to_state: Estado destino.

    Returns:
        True si la transición es válida, False en caso contrario.
    """
    if from_state not in VALID_STATE_TRANSITIONS:
        return False
    return to_state in VALID_STATE_TRANSITIONS[from_state]


def get_allowed_transitions(from_state: ProjectState) -> Set[ProjectState]:
    """
    Obtiene los estados permitidos desde un estado dado.

    Args:
        from_state: Estado actual.

    Returns:
        Set de estados permitidos como destino.
    """
    return VALID_STATE_TRANSITIONS.get(from_state, set())


def validate_state_transition(
    from_state: ProjectState,
    to_state: ProjectState,
) -> None:
    """
    Valida una transición de estado, lanzando excepción si no es válida.

    Args:
        from_state: Estado actual.
        to_state: Estado destino.

    Raises:
        ValueError: Si la transición no es válida.
    """
    if not is_valid_state_transition(from_state, to_state):
        allowed = get_allowed_transitions(from_state)
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "ninguno"
        raise ValueError(
            f"Transición de estado inválida: '{from_state.value}' → '{to_state.value}'. "
            f"Transiciones permitidas desde '{from_state.value}': {allowed_str}"
        )


__all__ = [
    "VALID_STATE_TRANSITIONS",
    "ProjectStateTransitions",
    "is_valid_state_transition",
    "get_allowed_transitions",
    "validate_state_transition",
]

# Fin del archivo backend\app\modules\projects\enums\project_state_transitions.py