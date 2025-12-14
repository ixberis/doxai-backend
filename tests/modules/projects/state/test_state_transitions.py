# backend\tests\modules\projects\state\test_state_transitions.py

import pytest
from app.modules.projects.enums import ProjectState, ProjectStateTransitions

@pytest.mark.parametrize("src,dst,allowed", [
    # Según tu matriz en project_state_transitions.py:
    # created → uploading
    (ProjectState.created, ProjectState.uploading, True),

    # ready → archived
    (ProjectState.ready, ProjectState.archived, True),

    # archived es terminal (no permite volver a ready)
    (ProjectState.archived, ProjectState.ready, False),

    # Algunos checks útiles adicionales:
    # uploading → processing permitido
    (ProjectState.uploading, ProjectState.processing, True),
    # uploading → ready NO permitido directamente
    (ProjectState.uploading, ProjectState.ready, False),
    # error → processing permitido (reintento)
    (ProjectState.error, ProjectState.processing, True),
    # error → ready NO permitido directo
    (ProjectState.error, ProjectState.ready, False),
])
def test_state_transition_matrix(src, dst, allowed):
    allowed_set = ProjectStateTransitions.get(src, set())
    assert (dst in allowed_set) is allowed
# Fin del archivo backend/tests/modules/projects/state/test_state_transitions.py
