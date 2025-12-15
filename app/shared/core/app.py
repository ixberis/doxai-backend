# -*- coding: utf-8 -*-
"""
backend/app/shared/core/app.py

Factory para crear la aplicación FastAPI con ciclo de vida.

═══════════════════════════════════════════════════════════════════════════════
LIMPIEZA PREVENTIVA (2025-12-15)
═══════════════════════════════════════════════════════════════════════════════
Se eliminó la función `_include_module_routers()` que:
- Escaneaba dinámicamente `app/modules/*/routes/`
- Montaba automáticamente cualquier `router` encontrado
- Causaba montajes DUPLICADOS junto con master_routes.py

CONTEXTO: Aunque main.py actualmente NO usa `create_app()` (crea su propia
instancia de FastAPI), esta limpieza es PREVENTIVA para:
1. Evitar que futuros desarrolladores usen create_app() y reactiven el bug
2. Mantener un único punto de verdad para montaje: master_routes.py
3. Eliminar código muerto que generaba confusión

El montaje de routers ahora ocurre EXCLUSIVAMENTE en:
  `backend/app/routes/master_routes.py`

Autor: Ixchel Beristáin
Fecha: 24/10/2025
Updated: 2025-12-15 - Eliminado montaje automático de routers (limpieza preventiva)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)


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
    """
    Crea una instancia de FastAPI con ciclo de vida.
    
    NOTA: Esta función NO monta routers automáticamente.
    El montaje se hace en main.py via app.routes.master_routes.
    
    Returns:
        FastAPI: Instancia configurada sin routers.
    """
    app = FastAPI(
        title="DoxAI Backend (modular)",
        lifespan=lifespan
    )
    # NO se llama a _include_module_routers(app)
    # Los routers se montan en main.py
    return app


# Fin del archivo backend/app/shared/core/app.py
