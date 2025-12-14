# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/embedding_provider.py

Proveedor de embeddings con soporte para múltiples backends.
Genera vectores para búsqueda semántica.

Autor: DoxAI
Fecha: 2025-10-28
"""

from typing import List
import aiohttp


class EmbeddingProvider:
    """
    Proveedor de embeddings con soporte para OpenAI y Azure OpenAI.
    
    Modelos soportados:
        - text-embedding-3-large (1536d, 3072d)
        - text-embedding-3-small (512d, 1536d)
        - text-embedding-ada-002 (1536d, legacy)
    """
    
    def __init__(
        self,
        provider: str = "openai",  # "openai" o "azure"
        api_key: str = None,
        endpoint: str = None,
        default_model: str = "text-embedding-3-large",
        default_dimension: int = 1536
    ):
        """
        Inicializa el proveedor de embeddings.
        
        Args:
            provider: Proveedor ("openai" o "azure")
            api_key: API key del proveedor
            endpoint: Endpoint (para Azure)
            default_model: Modelo por defecto
            default_dimension: Dimensión por defecto del vector
        """
        self.provider = provider
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.openai.com/v1"
        self.default_model = default_model
        self.default_dimension = default_dimension
    
    async def embed_texts(
        self,
        texts: List[str],
        model: str = None,
        dimension: int = None
    ) -> List[List[float]]:
        """
        Genera embeddings para lista de textos.
        
        Args:
            texts: Lista de textos a embedir
            model: Modelo a usar (usa default si None)
            dimension: Dimensión del vector (usa default si None)
            
        Returns:
            Lista de vectores (cada vector es List[float])
            
        Raises:
            NotImplementedError: Pendiente implementación
            ValueError: Si dimension no es válida para el modelo
            
        Notes:
            - Procesa en batches para eficiencia
            - Valida dimensión vs modelo
            - Maneja rate limits y reintentos
        """
        model = model or self.default_model
        dimension = dimension or self.default_dimension
        
        # Validar dimensión según modelo
        self._validate_dimension(model, dimension)
        
        # TODO: Implementación completa
        # 1. Dividir texts en batches (max 2048 tokens por request)
        # 2. Llamar a API del proveedor:
        #    - OpenAI: POST /v1/embeddings
        #    - Azure: POST {endpoint}/openai/deployments/{model}/embeddings
        # 3. Extraer vectores del response
        # 4. Validar que todos tienen la dimensión esperada
        # 5. Retornar lista de vectores
        
        raise NotImplementedError(
            f"Embedding generation pending for provider={self.provider}, model={model}"
        )
    
    def _validate_dimension(self, model: str, dimension: int):
        """Valida que la dimensión sea válida para el modelo."""
        valid_dims = {
            "text-embedding-3-large": [256, 1024, 1536, 3072],
            "text-embedding-3-small": [256, 512, 1536],
            "text-embedding-ada-002": [1536],
        }
        
        if model not in valid_dims:
            raise ValueError(f"Unknown model: {model}")
        
        if dimension not in valid_dims[model]:
            raise ValueError(
                f"Invalid dimension {dimension} for model {model}. "
                f"Valid dimensions: {valid_dims[model]}"
            )
    
    async def embed_query(self, query: str, model: str = None) -> List[float]:
        """
        Genera embedding para una consulta única.
        
        Args:
            query: Texto de la consulta
            model: Modelo a usar
            
        Returns:
            Vector de embedding
        """
        results = await self.embed_texts([query], model=model)
        return results[0] if results else []
