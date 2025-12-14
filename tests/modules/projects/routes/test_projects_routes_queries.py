
# -*- coding: utf-8 -*-
import uuid
import pytest

from app.modules.projects.routes import queries as routes_queries

def test_list_projects_for_user_ok(client):
    r = client.get("/projects?include_total=true&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "items" in body and isinstance(body["items"], list)
    assert "total" in body

def test_list_ready_projects_ok(client):
    r = client.get("/projects/ready?include_total=true")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["items"]) >= 1
    # al menos uno debe venir "ready"
    assert any(i.get("state") == "ready" for i in body["items"])

def test_list_actions_ok(client):
    pid = str(uuid.uuid4())
    r = client.get(f"/projects/{pid}/actions")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["total"] >= 1

def test_list_file_events_ok(client):
    pid = str(uuid.uuid4())
    r = client.get(f"/projects/{pid}/file-events")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["total"] >= 1

