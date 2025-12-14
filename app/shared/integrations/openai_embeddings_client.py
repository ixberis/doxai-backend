# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/openai_embeddings_client.py

Cliente para generar embeddings con OpenAI API.
Soporta modelos text-embedding-3-large, text-embedding-3-small.

Autor: DoxAI
Fecha: 2025-11-28
"""

import logging
from typing import List, Optional
import aiohttp

logger = logging.getLogger(__name__)


async def generate_embeddings(
    texts: List[str],
    *,
    api_key: str,
    model: str = "text-embedding-3-large",
    dimension: int = 1536,
    endpoint: str = "https://api.openai.com/v1",
    max_retries: int = 3,
) -> List[List[float]]:
    """
    Genera embeddings para una lista de textos usando OpenAI API.
    
    Args:
        texts: Lista de textos a embedir (máx ~8192 tokens por texto)
        api_key: API key de OpenAI
        model: Modelo de embeddings (default: text-embedding-3-large)
        dimension: Dimensión del vector (default: 1536)
        endpoint: Base URL de la API (default: https://api.openai.com/v1)
        max_retries: Número de reintentos en caso de error transitorio
        
    Returns:
        Lista de vectores (cada vector es List[float] de longitud `dimension`)
        
    Raises:
        ValueError: Si texts está vacío o dimension inválida
        RuntimeError: Si la API devuelve error no recuperable
        TimeoutError: Si el request tarda demasiado
        
    Notes:
        - Valida dimension vs model antes de llamar a la API
        - Maneja rate limits con backoff exponencial
        - Batch size recomendado: 100-200 textos por llamada
    """
    if not texts:
        raise ValueError("texts no puede estar vacío")
    
    # Validar dimensión
    _validate_dimension(model, dimension)
    
    logger.info(
        f"Generando embeddings OpenAI: {len(texts)} texts, "
        f"model={model}, dimension={dimension}"
    )
    
    url = f"{endpoint.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": texts,
        "model": model,
        "dimensions": dimension,
    }
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        embeddings = [item["embedding"] for item in result["data"]]
                        
                        # Validar que todos tienen la dimensión esperada
                        for i, emb in enumerate(embeddings):
                            if len(emb) != dimension:
                                raise RuntimeError(
                                    f"Embedding {i} tiene dimensión {len(emb)}, "
                                    f"esperada {dimension}"
                                )
                        
                        logger.info(
                            f"Embeddings OpenAI generados exitosamente: "
                            f"{len(embeddings)} vectores"
                        )
                        return embeddings
                    
                    # Rate limit o error de servidor: reintentar
                    if resp.status in [429, 500, 502, 503] and attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        error_text = await resp.text()
                        logger.warning(
                            f"OpenAI error {resp.status} (retry {attempt+1}/{max_retries}): "
                            f"{error_text}. Esperando {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Error no recuperable
                    error_text = await resp.text()
                    raise RuntimeError(
                        f"OpenAI Embeddings API error {resp.status}: {error_text}"
                    )
            
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout en intento {attempt+1}/{max_retries}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise TimeoutError("OpenAI Embeddings API timeout")
        
        raise RuntimeError("No se pudieron generar embeddings después de reintentos")


def _validate_dimension(model: str, dimension: int):
    """Valida que la dimensión sea válida para el modelo especificado."""
    valid_dims = {
        "text-embedding-3-large": [256, 1024, 1536, 3072],
        "text-embedding-3-small": [256, 512, 1536],
        "text-embedding-ada-002": [1536],
    }
    
    if model not in valid_dims:
        raise ValueError(f"Modelo desconocido: {model}")
    
    if dimension not in valid_dims[model]:
        raise ValueError(
            f"Dimensión {dimension} inválida para modelo {model}. "
            f"Dimensiones válidas: {valid_dims[model]}"
        )


# Import asyncio for sleep
import asyncio
