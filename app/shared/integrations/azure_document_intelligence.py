# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/azure_document_intelligence.py

Cliente para Azure Document Intelligence (Cognitive Services OCR).
Soporta análisis de documentos con extracción de texto, tablas y layout.

Autor: DoxAI
Fecha: 2025-11-28
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import aiohttp

from .azure_types import (
    AzureAnalysisStatus,
    AzureModelId,
    AzureDocumentResult,
)

logger = logging.getLogger(__name__)


@dataclass
class AzureOcrResult:
    """Resultado de análisis OCR de Azure Document Intelligence."""
    text: str  # Texto completo extraído
    pages: list[Dict[str, Any]]  # Páginas con metadatos
    confidence: Optional[float] = None
    lang: Optional[str] = None
    model_used: str = "prebuilt-read"


class AzureDocumentIntelligenceClient:
    """
    Cliente async para Azure Document Intelligence API.
    
    Uso:
        client = AzureDocumentIntelligenceClient(endpoint, api_key)
        result = await client.analyze_document(file_uri, strategy="balanced")
    """
    
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        *,
        api_version: str = "2024-07-31-preview",
        timeout_sec: int = 300,
        max_retries: int = 3,
        polling_interval_sec: int = 2,
    ):
        """
        Inicializa el cliente de Azure Document Intelligence.
        
        Args:
            endpoint: URL del endpoint (ej: https://<resource>.cognitiveservices.azure.com/)
            api_key: API key de Azure
            api_version: Versión de la API (default: 2024-07-31-preview)
            timeout_sec: Timeout total para el análisis (default: 300s)
            max_retries: Reintentos en caso de error transitorio (default: 3)
            polling_interval_sec: Intervalo de polling para resultados (default: 2s)
        """
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.api_version = api_version
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.polling_interval_sec = polling_interval_sec
        
        self.headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
    
    async def analyze_document(
        self,
        file_uri: str,
        *,
        locale: Optional[str] = None,
        strategy: str = "balanced",
        pages: Optional[str] = None,
    ) -> AzureOcrResult:
        """
        Analiza un documento usando Azure Document Intelligence.
        
        Args:
            file_uri: URI público del archivo o bytes base64
            locale: Código de idioma (ej: "en-US", "es-ES")
            strategy: Estrategia de optimización ("fast", "accurate", "balanced")
            pages: Rango de páginas a procesar (ej: "1-5,8")
            
        Returns:
            AzureOcrResult con texto extraído y metadatos
            
        Raises:
            ValueError: Si el archivo no está accesible o formato inválido
            TimeoutError: Si el análisis tarda más del timeout
            RuntimeError: Si Azure devuelve error no recuperable
        """
        model_id = self._get_model_id(strategy)
        
        logger.info(
            f"Iniciando análisis Azure OCR: file_uri={file_uri}, "
            f"model={model_id}, locale={locale}"
        )
        
        # 1. Iniciar análisis
        operation_location = await self._start_analysis(
            file_uri=file_uri,
            model_id=model_id,
            locale=locale,
            pages=pages,
        )
        
        # 2. Polling hasta completar
        result = await self._poll_analysis(operation_location)
        
        # 3. Parsear resultado
        ocr_result = self._parse_result(result, model_id)
        
        logger.info(
            f"Análisis Azure OCR completado: {len(ocr_result.text)} chars, "
            f"{len(ocr_result.pages)} pages"
        )
        
        return ocr_result
    
    async def _start_analysis(
        self,
        file_uri: str,
        model_id: str,
        locale: Optional[str],
        pages: Optional[str],
    ) -> str:
        """
        Inicia el análisis y retorna operation_location para polling.
        
        FASE C: Implementa retry con backoff exponencial para errores transitorios:
        - 429 (rate limiting)
        - 5xx (errores de servidor)
        - Timeouts
        """
        url = f"{self.endpoint}/documentintelligence/documentModels/{model_id}:analyze"
        params = {"api-version": self.api_version}
        
        payload: Dict[str, Any] = {"urlSource": file_uri}
        if locale:
            payload["locale"] = locale
        if pages:
            payload["pages"] = pages
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(self.max_retries):
                try:
                    async with session.post(
                        url,
                        headers=self.headers,
                        params=params,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 202:
                            operation_location = resp.headers.get("Operation-Location")
                            if not operation_location:
                                raise RuntimeError("Missing Operation-Location header")
                            return operation_location
                        
                        error_text = await resp.text()
                        
                        # FASE C: Detectar errores transitorios (429, 5xx)
                        is_rate_limit = resp.status == 429
                        is_server_error = resp.status >= 500
                        is_transient = is_rate_limit or is_server_error
                        
                        if is_transient and attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            error_type = "Rate limit (429)" if is_rate_limit else f"Server error ({resp.status})"
                            logger.warning(
                                f"[Azure OCR] {error_type} - Retry {attempt+1}/{self.max_retries} "
                                f"after {wait_time}s: {error_text[:200]}"
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        
                        # Error no transitorio o agotados los reintentos
                        raise RuntimeError(
                            f"Azure Document Intelligence error {resp.status}: {error_text}"
                        )
                
                except asyncio.TimeoutError:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(
                            f"[Azure OCR] Timeout - Retry {attempt+1}/{self.max_retries} after {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise TimeoutError("Azure Document Intelligence timeout al iniciar análisis")
        
        raise RuntimeError("No se pudo iniciar análisis Azure después de reintentos")
    
    async def _poll_analysis(self, operation_location: str) -> AzureDocumentResult:
        """Hace polling hasta que el análisis se complete."""
        start_time = asyncio.get_event_loop().time()
        
        async with aiohttp.ClientSession() as session:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self.timeout_sec:
                    raise TimeoutError(
                        f"Azure análisis timeout después de {self.timeout_sec}s"
                    )
                
                async with session.get(
                    operation_location,
                    headers={"Ocp-Apim-Subscription-Key": self.api_key},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise RuntimeError(
                            f"Error polling Azure status {resp.status}: {error_text}"
                        )
                    
                    result = await resp.json()
                    status = result.get("status", "")
                    
                    if status == AzureAnalysisStatus.SUCCEEDED.value:
                        return result
                    
                    if status in [
                        AzureAnalysisStatus.FAILED.value,
                        AzureAnalysisStatus.CANCELED.value,
                    ]:
                        raise RuntimeError(f"Azure análisis falló con status: {status}")
                    
                    # En progreso: esperar antes de siguiente poll
                    await asyncio.sleep(self.polling_interval_sec)
    
    def _parse_result(
        self,
        result: AzureDocumentResult,
        model_used: str,
    ) -> AzureOcrResult:
        """Parsea la respuesta de Azure a formato interno."""
        analyze_result = result.get("analyzeResult", {})
        
        # Extraer texto completo
        content = analyze_result.get("content", "")
        
        # Extraer páginas
        pages = analyze_result.get("pages", [])
        pages_metadata = [
            {
                "page_number": p.get("pageNumber", i + 1),
                "width": p.get("width"),
                "height": p.get("height"),
                "unit": p.get("unit", "pixel"),
                "angle": p.get("angle", 0),
                "lines": len(p.get("lines", [])),
                "words": len(p.get("words", [])),
            }
            for i, p in enumerate(pages)
        ]
        
        # Calcular confianza promedio si hay palabras
        all_words = [w for p in pages for w in p.get("words", [])]
        avg_confidence = None
        if all_words:
            confidences = [w.get("confidence", 0) for w in all_words if "confidence" in w]
            avg_confidence = sum(confidences) / len(confidences) if confidences else None
        
        # Detectar idioma (si está disponible en result)
        lang = analyze_result.get("languages", [{}])[0].get("locale") if analyze_result.get("languages") else None
        
        return AzureOcrResult(
            text=content,
            pages=pages_metadata,
            confidence=avg_confidence,
            lang=lang,
            model_used=model_used,
        )
    
    def _get_model_id(self, strategy: str) -> str:
        """Mapea estrategia a model_id de Azure."""
        mapping = {
            "fast": AzureModelId.PREBUILT_READ.value,
            "accurate": AzureModelId.PREBUILT_DOCUMENT.value,
            "balanced": AzureModelId.PREBUILT_READ.value,
        }
        return mapping.get(strategy, AzureModelId.PREBUILT_READ.value)
