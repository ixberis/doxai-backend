# -*- coding: utf-8 -*-
"""
backend/app/shared/core/model_singletons_cache.py

Singletons thread-safe para modelos de Unstructured.
Gestiona carga única y reutilización de Table Agent y Fast Parser.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import threading
import logging

logger = logging.getLogger(__name__)

# Thread-safe locks para evitar race conditions
_table_agent_lock = threading.Lock()
_table_agent_loaded = False


def quiet_pdf_parsers() -> None:
    """Silencia los warnings molestos de pdfminer."""
    for name in ("pdfminer", "pdfminer.pdffont", "pdfminer.psparser", "pdfminer.cmapdb"):
        logging.getLogger(name).setLevel(logging.ERROR)


def get_warmup_asset_path() -> Path:
    """Obtiene la ruta al PDF de warm-up."""
    current_dir = Path(__file__).parent  # .../app/shared/core
    asset_path = current_dir.parent.parent / "assets" / "warmup" / "warmup_es_min.pdf"
    return asset_path


def get_singleton_table_agent():
    """
    Obtiene/asegura el Table Agent precargado durante warm-up.
    Añade logging para confirmar uso del singleton.
    """
    result = get_table_agent()  # Usa el singleton cacheado
    if result:
        logger.debug("🔁 Usando Table Agent desde cache (singleton)")
    return result


def get_table_agent():
    """
    Singleton thread-safe para el agente de tablas de Unstructured.
    Se carga una sola vez y se reutiliza en todo el proceso.
    Evita race conditions con lock explícito.
    Devuelve True si cargó correctamente, False si no.
    """
    global _table_agent_loaded

    # Thread-safe check rápido (double-checked locking pattern)
    if _table_agent_loaded:
        return True

    with _table_agent_lock:
        # Re-check dentro del lock por si otro thread ya cargó
        if _table_agent_loaded:
            return True

        try:
            logger.info("📊 Cargando Table Agent (singleton thread-safe)...")

            # Forzar la carga del modelo interno de tablas de unstructured
            from unstructured.partition.utils.config import env_config
            from unstructured.partition.pdf import partition_pdf

            # Trigger de carga: procesar una página con infer_table_structure=True
            test_path = get_warmup_asset_path()
            if test_path.exists():
                partition_pdf(
                    filename=str(test_path),
                    strategy="hi_res",
                    pages=[1],
                    infer_table_structure=True,
                    languages=["spa"],  # Español fijo
                    detect_language_per_page=False,
                    pdf_infer_table_structure_kwargs={
                        "size": {"longest_edge": 2048}
                    },
                )
            else:
                logger.info("⚠️ Warm-up sin asset: se omite partition_pdf, el modelo Table Agent se inicializará on-demand")

            # Bandera para evitar recargas innecesarias (internals de Unstructured)
            # Nota: Acceso a internals protegido para cambios futuros de API
            try:
                if hasattr(env_config, "_table_model_loaded"):
                    setattr(env_config, "_table_model_loaded", True)
                else:
                    logger.debug("⚠️ env_config._table_model_loaded no disponible (versión de Unstructured cambió)")
            except (AttributeError, Exception) as e:
                logger.debug(f"⚠️ No se pudo establecer _table_model_loaded: {e}")
            
            _table_agent_loaded = True  # Marcar como cargado

            logger.info("✅ Table Agent cargado (singleton thread-safe) [size.longest_edge=2048]")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Error cargando Table Agent: {e}")
            return False


@lru_cache(maxsize=1)
def get_fast_parser():
    """
    Singleton para el parser rápido de Unstructured.
    Se carga una sola vez y se reutiliza en todo el proceso.
    Devuelve True si cargó correctamente, False si no.
    """
    try:
        logger.info("⚡ Cargando Fast Parser (singleton)...")

        from unstructured.partition.pdf import partition_pdf

        # Warm up fast parser with test document
        test_path = get_warmup_asset_path()
        if test_path.exists():
            partition_pdf(
                filename=str(test_path),
                strategy="fast",
                pages=[1],
                languages=["spa"],  # Español fijo
                detect_language_per_page=False,
            )
        else:
            logger.info("⚠️ Warm-up sin asset: se omite partition_pdf, el Fast Parser se inicializará on-demand")

        logger.info("✅ Fast Parser cargado (singleton)")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Error cargando Fast Parser: {e}")
        return False


def get_standard_language_config() -> dict:
    """
    Configuración estándar de idioma para todas las llamadas a Unstructured.
    Fuerza español sin detección por página para evitar ramas innecesarias.
    """
    return {
        "languages": ["spa"],  # Solo español, evita warning deprecado de ocr_languages
        "detect_language_per_page": False,  # Evita detección innecesaria
    }


# Funciones de compatibilidad para el código existente
def warmup_unstructured(load_table_model: bool = None) -> None:
    """
    Función de compatibilidad - asegura que los modelos estén cargados.
    """
    get_fast_parser()  # Load fast parser
    if load_table_model is not False:
        get_table_agent()  # Load table agent


def ensure_table_model_loaded() -> None:
    """
    Asegura que el modelo de tablas esté cargado usando singleton.
    Incluye logging para confirmar uso del singleton.
    """
    get_singleton_table_agent()  # Force load using singleton with logging


# Fin del archivo backend/app/shared/core/model_singletons_cache.py
