# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/azure_ocr_service.py

Servicio para OCR con Azure Cognitive Services (Document Intelligence).
Ejecuta OCR con estrategias configurables para documentos escaneados o imágenes.

Autor: DoxAI
Fecha: 2025-10-28
"""

from typing import Optional
import aiohttp
from dataclasses import dataclass

from app.modules.rag.enums import OcrOptimization


@dataclass
class OcrResult:
    """Resultado de OCR con metadatos de calidad."""
    result_uri: str
    lang: Optional[str] = None
    confidence: Optional[float] = None


class AzureOcrService:
    """
    Servicio para ejecutar OCR con Azure Cognitive Services.
    
    Estrategias:
        - fast: Optimizado para velocidad (prebuilt-read)
        - accurate: Máxima precisión (prebuilt-document)
        - balanced: Balance velocidad/precisión (prebuilt-read con mayor confianza)
    """
    
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        default_strategy: OcrOptimization = OcrOptimization.balanced
    ):
        """
        Inicializa el servicio de OCR.
        
        Args:
            endpoint: URL del endpoint de Azure Cognitive Services
            api_key: API key de Azure
            default_strategy: Estrategia por defecto
        """
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.default_strategy = default_strategy
    
    async def run_ocr(
        self,
        source_uri: str,
        strategy: Optional[OcrOptimization] = None
    ) -> OcrResult:
        """
        Ejecuta OCR sobre documento escaneado o imagen.
        
        Args:
            source_uri: URI del archivo fuente (PDF/imagen)
            strategy: Estrategia de optimización (usa default si None)
            
        Returns:
            OcrResult con URI del resultado, idioma detectado y confianza
            
        Raises:
            NotImplementedError: Pendiente implementación completa
            
        Notes:
            - Usa Azure Document Intelligence API
            - Guarda resultado en storage (result_uri)
            - Idempotente por (source_uri, strategy)
        """
        strat = strategy or self.default_strategy
        
        # TODO: Implementación completa
        # 1. Determinar modelo según strategy:
        #    - fast: prebuilt-read
        #    - accurate: prebuilt-document
        #    - balanced: prebuilt-read con validación de confianza
        # 2. Llamar a Azure Document Intelligence REST API
        # 3. Extraer texto, lang y confidence del response
        # 4. Guardar resultado en storage (result_uri)
        # 5. Retornar OcrResult
        
        raise NotImplementedError(
            f"Azure OCR pending implementation for strategy={strat.value}, source={source_uri}"
        )
    
    def _get_model_id(self, strategy: OcrOptimization) -> str:
        """Mapea estrategia a modelo de Azure."""
        mapping = {
            OcrOptimization.fast: "prebuilt-read",
            OcrOptimization.accurate: "prebuilt-document",
            OcrOptimization.balanced: "prebuilt-read",
        }
        return mapping.get(strategy, "prebuilt-read")
