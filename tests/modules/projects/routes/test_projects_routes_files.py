
# -*- coding: utf-8 -*-
import uuid
import pytest

from app.modules.projects.routes import files as routes_files

def test_list_files_ok(client):
    pid = str(uuid.uuid4())
    r = client.get(f"/projects/{pid}/files")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert isinstance(data["items"], list)
    assert data["total"] >= 1

def test_add_file_ok(client):
    pid = str(uuid.uuid4())
    payload = {"path": "users/u/a.pdf", "filename": "a.pdf"}
    r = client.post(f"/projects/{pid}/files", json=payload)
    assert r.status_code == 201
    assert r.json()["success"] is True
    assert "file_id" in r.json()

def test_validate_file_ok(client):
    fid = str(uuid.uuid4())
    r = client.post(f"/projects/files/{fid}/validate")
    assert r.status_code == 200
    assert r.json()["file_id"] == fid

def test_move_file_ok(client):
    fid = str(uuid.uuid4())
    payload = {"new_path": "users/u/b.pdf"}
    r = client.post(f"/projects/files/{fid}/move", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["new_path"] == "users/u/b.pdf"

def test_delete_file_ok(client):
    fid = str(uuid.uuid4())
    r = client.delete(f"/projects/files/{fid}")
    assert r.status_code == 200
    assert r.json()["success"] is True
