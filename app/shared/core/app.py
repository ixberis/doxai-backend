# -*- coding: utf-8 -*-
"""
backend/app/shared/core/app.py

Factory para crear la aplicación FastAPI con módulos cargados dinámicamente.

Autor: Ixchel Beristáin
Fecha: 24/10/2025
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from importlib import import_module
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def _include_module_routers(app: FastAPI) -> None:
    base = Path(__file__).resolve().parents[2] / "modules"
    if not base.exists():
        return
    for pkg in base.iterdir():
        if not (pkg.is_dir() and (pkg / "routes").exists()):
            continue
        # 1) intentar __init__.py con `router`
        try:
            mod = import_module(f"app.modules.{pkg.name}.routes")
            router = getattr(mod, "router", None)
            if router:
                app.include_router(router)
        except ModuleNotFoundError:
            pass
        # 2) incluir todos los *.py que exporten `router`
        for py in (pkg / "routes").glob("*.py"):
            if py.name == "__init__.py":
                continue
            try:
                m = import_module(f"app.modules.{pkg.name}.routes.{py.stem}")
                r = getattr(m, "router", None)
                if r:
                    app.include_router(r)
            except ModuleNotFoundError:
                continue

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: warm-up al inicio, shutdown al cierre."""
    # Startup: ejecutar warm-up
    logger.info("🚀 Iniciando warm-up de recursos...")
    try:
        from .resource_cache import run_warmup_once
        status = await run_warmup_once()
        if status.is_ready:
            logger.info("✅ Warm-up completado exitosamente")
        else:
            logger.warning("⚠️ Warm-up completado con advertencias")
    except Exception as e:
        logger.error(f"❌ Error durante warm-up: {e}")
    
    yield
    
    # Shutdown: limpiar recursos
    logger.info("🛑 Cerrando recursos globales...")
    try:
        from .resource_cache import shutdown_all
        await shutdown_all()
        logger.info("✅ Recursos cerrados correctamente")
    except Exception as e:
        logger.error(f"❌ Error durante shutdown: {e}")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DoxAI Backend (modular)",
        lifespan=lifespan
    )
    _include_module_routers(app)
    return app
