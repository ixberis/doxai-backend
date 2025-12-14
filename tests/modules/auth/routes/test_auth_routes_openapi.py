
# backend/tests/modules/auth/routes/test_auth_routes_openapi.py
# -*- coding: utf-8 -*-

from fastapi import FastAPI
from importlib import import_module

def build_app() -> FastAPI:
    app = FastAPI(title="DoxAI Test App - Auth Routes")
    # Importamos routers del módulo
    auth_public = import_module("app.modules.auth.routes.auth_public").router
    auth_tokens = import_module("app.modules.auth.routes.auth_tokens").router
    auth_admin = import_module("app.modules.auth.routes.auth_admin").router

    app.include_router(auth_public)
    app.include_router(auth_tokens)
    app.include_router(auth_admin)
    return app

def test_openapi_has_expected_auth_paths():
    app = build_app()
    spec = app.openapi()
    paths = spec.get("paths", {})

    # Rutas públicas
    assert "/auth/register" in paths and "post" in paths["/auth/register"]
    assert "/auth/activation" in paths and "post" in paths["/auth/activation"]
    assert "/auth/activation/resend" in paths and "post" in paths["/auth/activation/resend"]
    assert "/auth/password/forgot" in paths and "post" in paths["/auth/password/forgot"]
    assert "/auth/password/reset" in paths and "post" in paths["/auth/password/reset"]

    # Rutas de tokens / sesión
    assert "/auth/login" in paths and "post" in paths["/auth/login"]
    assert "/auth/token/refresh" in paths and "post" in paths["/auth/token/refresh"]
    assert "/auth/logout" in paths and "post" in paths["/auth/logout"]
    assert "/auth/me" in paths and "get" in paths["/auth/me"]

    # Rutas admin (auditoría)
    assert "/auth/admin/sessions/revoke-all" in paths and "post" in paths["/auth/admin/sessions/revoke-all"]
    assert "/auth/admin/login-attempts" in paths and "get" in paths["/auth/admin/login-attempts"]
    assert "/auth/admin/sessions" in paths and "get" in paths["/auth/admin/sessions"]

# Fin del archivo backend/tests/modules/auth/routes/test_auth_routes_openapi.py
