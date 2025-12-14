# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/text_extractors.py

Extractores de texto nativo (sin OCR) para diversos formatos.
Convierte documentos binarios a texto usando su estructura nativa.

Autor: DoxAI
Fecha: 2025-10-28
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class ExtractedText:
    """Resultado de extracción de texto."""
    result_uri: str
    byte_size: int
    checksum: str


class TextExtractorService:
    """
    Servicio para extraer texto nativo de documentos.
    
    Formatos soportados:
        - PDF: PyPDF2/pdfplumber para texto nativo
        - DOCX: python-docx
        - TXT: lectura directa
        - HTML/XML: BeautifulSoup
    """
    
    def __init__(self, storage_service):
        """
        Inicializa el servicio de extracción.
        
        Args:
            storage_service: Servicio de almacenamiento para leer/escribir
        """
        self.storage = storage_service
    
    async def extract_text(
        self,
        document_file_id: UUID,
        source_uri: str,
        mime_type: str
    ) -> ExtractedText:
        """
        Extrae texto nativo de documento sin OCR.
        
        Args:
            document_file_id: ID del archivo a procesar
            source_uri: URI del archivo fuente en storage
            mime_type: Tipo MIME del documento
            
        Returns:
            ExtractedText con URI del resultado, tamaño y checksum
            
        Raises:
            NotImplementedError: Pendiente implementación
            ValueError: Si el mime_type no es soportado
            
        Notes:
            - No incluye OCR (documentos escaneados requieren fase OCR)
            - Idempotente por checksum del source
            - Guarda resultado en storage con path predecible
        """
        # TODO: Implementación completa
        # 1. Detectar extractor apropiado por mime_type
        # 2. Descargar archivo de source_uri
        # 3. Extraer texto según formato:
        #    - PDF: PyPDF2.PdfReader o pdfplumber
        #    - DOCX: python-docx
        #    - TXT/MD: lectura directa
        #    - HTML/XML: BeautifulSoup
        # 4. Guardar texto en storage (result_uri)
        # 5. Calcular checksum (SHA-256) y byte_size
        # 6. Retornar ExtractedText
        
        raise NotImplementedError(
            f"Text extraction pending for mime_type={mime_type}, file_id={document_file_id}"
        )
    
    def _get_extractor(self, mime_type: str):
        """Resuelve extractor apropiado por mime_type."""
        extractors = {
            "application/pdf": self._extract_pdf,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": self._extract_docx,
            "text/plain": self._extract_text,
            "text/markdown": self._extract_text,
            "text/html": self._extract_html,
        }
        
        extractor = extractors.get(mime_type)
        if not extractor:
            raise ValueError(f"Unsupported mime_type: {mime_type}")
        return extractor
    
    async def _extract_pdf(self, file_path: str) -> str:
        """Extrae texto de PDF usando PyPDF2/pdfplumber."""
        raise NotImplementedError("PDF extraction pending")
    
    async def _extract_docx(self, file_path: str) -> str:
        """Extrae texto de DOCX usando python-docx."""
        raise NotImplementedError("DOCX extraction pending")
    
    async def _extract_text(self, file_path: str) -> str:
        """Lee texto plano directamente."""
        raise NotImplementedError("Text extraction pending")
    
    async def _extract_html(self, file_path: str) -> str:
        """Extrae texto de HTML usando BeautifulSoup."""
        raise NotImplementedError("HTML extraction pending")
