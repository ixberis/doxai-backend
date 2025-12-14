
# backend/tests/modules/projects/enums/test_project_enums.py

import importlib
import enum


def test_project_enums_export_surface():
    m = importlib.import_module("app.modules.projects.enums")
    # Export keys esperados en Projects v2
    expected = {
        "ProjectActionType",
        "ProjectFileEvent",
        "ProjectState",
        "ProjectStateTransitions",
        "ProjectStatus",
    }
    exported = {k for k in dir(m) if not k.startswith("_")}
    missing = expected - exported
    assert not missing, f"Faltan en __init__: {missing}"
    
    # ProjectFilter ya NO se exporta en Projects v2
    assert "ProjectFilter" not in exported, "ProjectFilter no debe estar en la surface pública de Projects v2"

def test_project_state_and_status_are_enums():
    from app.modules.projects.enums import ProjectState, ProjectStatus
    assert issubclass(ProjectState, enum.Enum)
    assert issubclass(ProjectStatus, enum.Enum)


def test_project_state_transitions_map_is_consistent():
    from app.modules.projects.enums import ProjectState, ProjectStateTransitions
    assert isinstance(ProjectStateTransitions, dict)
    # Cada clave en transiciones debe ser ProjectState y los destinos también.
    for src, dst_set in ProjectStateTransitions.items():
        assert isinstance(src, ProjectState), f"Clave no ProjectState: {src}"
        assert isinstance(dst_set, set)
        for dst in dst_set:
            assert isinstance(dst, ProjectState), f"Destino no ProjectState: {dst}"

# Fin del archivo backend/tests/modules/projects/enums/test_project_enums.py