
# -*- coding: utf-8 -*-
import uuid
import pytest

from app.modules.projects.routes import projects_lifecycle as routes_projects

def test_change_status_ok(client):
    pid = str(uuid.uuid4())
    # enum válido en tu ProjectStatus: 'in_process'
    r = client.post(f"/projects/{pid}/status/in_process")
    assert r.status_code == 200
    assert r.json()["project"]["status"] in ("in_process", "ProjectStatus.in_process", "IN_PROCESS")

def test_transition_state_ok(client):
    pid = str(uuid.uuid4())
    r = client.post(f"/projects/{pid}/state/ready")
    assert r.status_code == 200
    assert r.json()["project"]["state"] in ("ready", "ProjectState.ready", "READY")

def test_archive_ok(client):
    pid = str(uuid.uuid4())
    r = client.post(f"/projects/{pid}/archive")
    assert r.status_code == 200
    assert r.json()["project"]["state"] in ("archived", "ProjectState.archived", "ARCHIVED")
