# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_dispatcher_core.py

Core dispatcher logic for file type detection and routing.
Handles the main dispatch logic without conversion implementation details.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from conversion_dispatcher.py
"""

from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, List
import logging

logger = logging.getLogger(__name__)


class FileTypeRouter:
    """
    Determines which converter to use based on file type.
    Single responsibility: file type detection and routing.
    """
    
    # File type to converter mapping
    TYPE_MAPPING = {
        "pdf": "pdf",
        "docx": "word",
        "doc": "word", 
        "odt": "word",
        "xlsx": "excel",
        "xls": "excel",
        "ods": "excel",
        "csv": "excel",
        "pptx": "powerpoint",
        "ppt": "powerpoint",
        "odp": "powerpoint",
        "txt": "text"
    }
    
    # Stage mapping for progress callbacks
    STAGE_MAPPING = {
        "pdf": "conversion:pdf",
        "word": "conversion:word", 
        "excel": "conversion:excel",
        "powerpoint": "conversion:powerpoint",
        "text": "conversion:text"
    }
    
    @classmethod
    def get_converter_type(cls, file_type: str) -> Optional[str]:
        """
        Get converter type for a given file extension.
        
        Args:
            file_type: File extension (pdf, docx, etc.)
            
        Returns:
            Converter type (pdf, word, excel, powerpoint, text) or None
        """
        return cls.TYPE_MAPPING.get(file_type.lower())
    
    @classmethod
    def get_stage_name(cls, converter_type: str) -> str:
        """
        Get progress stage name for a converter type.
        
        Args:
            converter_type: Converter type (pdf, word, etc.)
            
        Returns:
            Stage name for progress reporting
        """
        return cls.STAGE_MAPPING.get(converter_type, "conversion:unknown")
    
    @classmethod
    def is_supported_file_type(cls, file_type: str) -> bool:
        """
        Check if file type is supported.
        
        Args:
            file_type: File extension to check
            
        Returns:
            True if supported, False otherwise
        """
        return file_type.lower() in cls.TYPE_MAPPING


class DispatcherConfig:
    """
    Configuration settings for the dispatcher.
    Centralized configuration management.
    """
    
    # Default progress messages by converter type
    PROGRESS_MESSAGES = {
        "pdf": {
            "start": "Iniciando conversión PDF robusta",
            "complete": "Conversión PDF completada"
        },
        "word": {
            "start": "Iniciando conversión Word", 
            "complete": "Conversión Word completada"
        },
        "excel": {
            "start": "Iniciando conversión Excel",
            "complete": "Conversión Excel completada"
        },
        "powerpoint": {
            "start": "Iniciando conversión PowerPoint",
            "complete": "Conversión PowerPoint completada"
        },
        "text": {
            "start": "Cargando archivo de texto",
            "complete": "Carga de texto completada"
        }
    }
    
    @classmethod
    def get_progress_message(cls, converter_type: str, stage: str) -> str:
        """
        Get localized progress message for converter type and stage.
        
        Args:
            converter_type: Type of converter (pdf, word, etc.)
            stage: Stage (start, complete)
            
        Returns:
            Localized progress message
        """
        messages = cls.PROGRESS_MESSAGES.get(converter_type, {})
        return messages.get(stage, f"Procesando {converter_type}")






