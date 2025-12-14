
# -*- coding: utf-8 -*-
import uuid
import types
import pytest

from app.modules.projects.routes import projects_crud as routes_projects

def test_create_project_ok(client, test_user_id, test_user_email):
    payload = {
        "project_name": "Nuevo",
        "project_slug": "nuevo",
        "project_description": "desc"
    }
    r = client.post("/projects", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["success"] is True
    assert body["project"]["project_name"] == "Nuevo"
    assert body["project"]["project_slug"] == "nuevo"

def test_get_project_by_id_found_same_owner(client, test_user_id):
    pid = str(uuid.uuid4())
    r = client.get(f"/projects/{pid}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == pid
    assert data["user_id"] == str(test_user_id)

def test_update_project_ok(client):
    pid = str(uuid.uuid4())
    payload = {"project_name": "Renombrado"}
    r = client.patch(f"/projects/{pid}", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["project"]["project_name"] == "Renombrado"

def test_delete_project_ok(client):
    pid = str(uuid.uuid4())
    r = client.delete(f"/projects/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
