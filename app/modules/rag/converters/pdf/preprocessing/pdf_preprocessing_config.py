# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_preprocessing_config.py

Configuration management for PDF image preprocessing operations.
Single responsibility: managing preprocessing settings and parameters.

Author: Ixchel Beristáin Mendoza  
Date: 28/09/2025 - Refactored from pdf_image_preprocessing.py
"""

import logging
from typing import Optional
from dataclasses import dataclass
from app.shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingConfig:
    """
    Configuration data class for PDF preprocessing operations.
    """
    # Rendering settings
    dpi: int = 300
    dpi_fallback: int = 200
    
    # Enhancement settings
    grayscale_enabled: bool = True
    deskew_enabled: bool = True
    binarize_enabled: bool = False
    noise_reduction_enabled: bool = True
    
    # Performance settings
    timeout_per_page: Optional[int] = None
    max_image_dimension: int = 4096
    
    # Color mode
    color_mode: str = "grayscale"  # "grayscale" or "color"


class PDFPreprocessingConfigManager:
    """
    Manages configuration for PDF preprocessing operations.
    Single responsibility: configuration loading and validation.
    """
    
    def __init__(self):
        """Initialize config manager with default settings."""
        self._config = self._load_config_from_settings()
    
    def _load_config_from_settings(self) -> PreprocessingConfig:
        """
        Load configuration from application settings.
        
        Returns:
            PreprocessingConfig instance with loaded settings
        """
        try:
            config = PreprocessingConfig()
            
            # Load OCR-related settings if available
            if hasattr(settings, 'ocr'):
                config.dpi = getattr(settings.ocr, 'dpi', config.dpi)
                config.dpi_fallback = getattr(settings.ocr, 'dpi_fallback', config.dpi_fallback)
                config.deskew_enabled = getattr(settings.ocr, 'deskew', config.deskew_enabled)
                config.binarize_enabled = getattr(settings.ocr, 'binarize', config.binarize_enabled)
                config.timeout_per_page = getattr(settings.ocr, 'page_timeout_seconds', config.timeout_per_page)
                
                # Handle color mode enum if present
                color_mode = getattr(settings.ocr, 'color_mode', None)
                if color_mode and hasattr(color_mode, 'value'):
                    config.color_mode = color_mode.value
                    config.grayscale_enabled = (color_mode.value == "grayscale")
            
            # Load general image processing settings
            if hasattr(settings, 'image_processing'):
                config.max_image_dimension = getattr(
                    settings.image_processing, 'max_dimension', config.max_image_dimension
                )
            
            logger.info(f"📋 Loaded preprocessing config: DPI={config.dpi}, "
                       f"grayscale={config.grayscale_enabled}, deskew={config.deskew_enabled}")
            
            return config
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load config from settings: {e}, using defaults")
            return PreprocessingConfig()
    
    def get_config(self) -> PreprocessingConfig:
        """
        Get current preprocessing configuration.
        
        Returns:
            Current PreprocessingConfig instance
        """
        return self._config
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration parameters.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
                    logger.debug(f"Updated config {key}={value}")
                else:
                    logger.warning(f"⚠️ Unknown config parameter: {key}")
        except Exception as e:
            logger.error(f"❌ Failed to update config: {e}")
    
    def get_render_settings(self) -> dict:
        """
        Get rendering-specific settings.
        
        Returns:
            Dictionary with rendering settings
        """
        return {
            'dpi': self._config.dpi,
            'dpi_fallback': self._config.dpi_fallback,
            'timeout_per_page': self._config.timeout_per_page,
            'max_image_dimension': self._config.max_image_dimension
        }
    
    def get_enhancement_settings(self) -> dict:
        """
        Get image enhancement settings.
        
        Returns:
            Dictionary with enhancement settings
        """
        return {
            'grayscale_enabled': self._config.grayscale_enabled,
            'deskew_enabled': self._config.deskew_enabled,
            'binarize_enabled': self._config.binarize_enabled,
            'noise_reduction_enabled': self._config.noise_reduction_enabled,
            'color_mode': self._config.color_mode
        }
    
    def validate_config(self) -> bool:
        """
        Validate current configuration settings.
        
        Returns:
            True if configuration is valid
        """
        try:
            config = self._config
            
            # Validate DPI settings
            if config.dpi <= 0 or config.dpi > 1200:
                logger.error(f"❌ Invalid DPI setting: {config.dpi}")
                return False
            
            if config.dpi_fallback <= 0 or config.dpi_fallback > config.dpi:
                logger.error(f"❌ Invalid fallback DPI: {config.dpi_fallback}")
                return False
            
            # Validate timeout
            if config.timeout_per_page is not None and config.timeout_per_page <= 0:
                logger.error(f"❌ Invalid timeout setting: {config.timeout_per_page}")
                return False
            
            # Validate max dimension
            if config.max_image_dimension <= 0 or config.max_image_dimension > 10000:
                logger.error(f"❌ Invalid max dimension: {config.max_image_dimension}")
                return False
            
            logger.debug("✅ Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Configuration validation failed: {e}")
            return False
    
    def get_config_summary(self) -> str:
        """
        Get human-readable configuration summary.
        
        Returns:
            Formatted configuration summary string
        """
        config = self._config
        
        return (
            f"PDF Preprocessing Configuration:\n"
            f"  📏 DPI: {config.dpi} (fallback: {config.dpi_fallback})\n"
            f"  🎨 Color mode: {config.color_mode}\n"
            f"  ⚙️ Enhancement: grayscale={config.grayscale_enabled}, "
            f"deskew={config.deskew_enabled}, binarize={config.binarize_enabled}\n"
            f"  ⏱️ Timeout: {config.timeout_per_page}s per page\n"
            f"  📐 Max dimension: {config.max_image_dimension}px"
        )






