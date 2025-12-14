
# backend/tests/modules/auth/routes/test_auth_routes_admin_stubs.py
# -*- coding: utf-8 -*-

from fastapi import FastAPI
from fastapi.testclient import TestClient
from importlib import import_module

def build_client() -> TestClient:
    app = FastAPI(title="DoxAI Test App - Auth Admin Stubs")
    auth_admin = import_module("app.modules.auth.routes.auth_admin").router
    app.include_router(auth_admin)
    return TestClient(app)

def test_login_attempts_returns_501_stub():
    client = build_client()
    # Sin parámetros: el stub devuelve 501
    r = client.get("/auth/admin/login-attempts")
    assert r.status_code == 501
    assert "no implementado" in r.json().get("detail", "").lower()

def test_sessions_returns_501_stub():
    client = build_client()
    r = client.get("/auth/admin/sessions")
    assert r.status_code == 501
    assert "no implementado" in r.json().get("detail", "").lower()

def test_revoke_all_sessions_returns_501_stub_without_body():
    client = build_client()
    # Aunque el real esperará body, validamos que el handler responda 501
    # usando un body vacío para no acoplar al schema.
    r = client.post("/auth/admin/sessions/revoke-all", json={})
    assert r.status_code == 501
    # El detalle puede venir por NotImplementedError o stub explícito
    # según la implementación final; validamos la forma general.
    detail = r.json().get("detail", "")
    assert detail
    assert "no implementado" in detail.lower() or "implementado" in detail.lower()

# Fin del archivo backend/tests/modules/auth/routes/test_auth_routes_admin_stubs.py
