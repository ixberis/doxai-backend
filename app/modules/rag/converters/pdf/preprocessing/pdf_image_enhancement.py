# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_image_enhancement.py

Image enhancement operations for PDF preprocessing.
Single responsibility: applying image processing techniques for OCR optimization.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_image_preprocessing.py
"""

import logging
from typing import Optional
import numpy as np
from app.shared.config import settings

logger = logging.getLogger(__name__)

# Check OpenCV availability
try:
    import cv2
    HAS_CV2 = True
except ImportError as e:
    logger.warning(f"⚠️ OpenCV not available: {e}. Image enhancement will be limited.")
    HAS_CV2 = False


class PDFImageEnhancer:
    """
    Applies image enhancement techniques for OCR optimization.
    Single responsibility: image processing operations.
    """
    
    def __init__(self):
        """Initialize enhancer with configuration."""
        pass
    
    def convert_to_grayscale(self, image: np.ndarray) -> np.ndarray:
        """
        Convert image to grayscale for faster OCR processing.
        
        Args:
            image: Input image array (RGB or already grayscale)
            
        Returns:
            Grayscale image array
        """
        try:
            if len(image.shape) == 3 and image.shape[2] == 3:
                # RGB to grayscale conversion
                if HAS_CV2:
                    grayscale = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                else:
                    # Fallback using numpy weighted average
                    grayscale = np.dot(image[...,:3], [0.2989, 0.5870, 0.1140])
                
                return grayscale.astype(np.uint8)
            
            # Already grayscale or single channel
            return image
            
        except Exception as e:
            logger.warning(f"⚠️ Grayscale conversion failed: {e}, using original image")
            return image
    
    def apply_deskewing(self, image: np.ndarray) -> np.ndarray:
        """
        Apply deskewing to correct document rotation using Hough line detection.
        
        Args:
            image: Input image array
            
        Returns:
            Deskewed image array
        """
        if not HAS_CV2:
            logger.warning("⚠️ OpenCV not available, skipping deskewing")
            return image
        
        try:
            # Ensure grayscale for edge detection
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            else:
                gray = image.copy()
            
            # Apply edge detection
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Detect lines using HoughLines
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
            
            if lines is not None and len(lines) > 0:
                # Calculate average angle of detected lines
                angles = []
                for line in lines[:10]:  # Use top 10 lines to avoid noise
                    rho, theta = line[0]
                    angle = np.degrees(theta) - 90
                    if abs(angle) < 45:  # Only consider reasonable angles
                        angles.append(angle)
                
                if angles:
                    avg_angle = np.median(angles)
                    
                    # Only correct if angle is significant (> 0.5 degrees)
                    if abs(avg_angle) > 0.5:
                        # Calculate rotation matrix and apply transformation
                        (h, w) = image.shape[:2]
                        center = (w // 2, h // 2)
                        M = cv2.getRotationMatrix2D(center, avg_angle, 1.0)
                        
                        # Rotate image
                        rotated = cv2.warpAffine(
                            image, M, (w, h), 
                            flags=cv2.INTER_CUBIC, 
                            borderMode=cv2.BORDER_REPLICATE
                        )
                        
                        if settings.logging.ocr_per_page:
                            logger.info(f"🔄 Applied deskewing: {avg_angle:.2f} degrees")
                        
                        return rotated
            
            # No significant skew detected
            return image
            
        except Exception as e:
            logger.warning(f"⚠️ Deskewing failed: {e}, using original image")
            return image
    
    def apply_binarization(self, image: np.ndarray) -> np.ndarray:
        """
        Apply Otsu binarization for better text recognition.
        
        Args:
            image: Input image array
            
        Returns:
            Binarized image array
        """
        if not HAS_CV2:
            logger.warning("⚠️ OpenCV not available, skipping binarization")
            return image
        
        try:
            # Ensure grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            else:
                gray = image.copy()
            
            # Apply Otsu's thresholding
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            if settings.logging.ocr_per_page:
                logger.info(f"🎯 Applied Otsu binarization")
            
            return binary
            
        except Exception as e:
            logger.warning(f"⚠️ Binarization failed: {e}, using original image")
            return image
    
    def apply_noise_reduction(self, image: np.ndarray) -> np.ndarray:
        """
        Apply light smoothing and noise reduction.
        
        Args:
            image: Input image array
            
        Returns:
            Smoothed image array
        """
        if not HAS_CV2:
            logger.warning("⚠️ OpenCV not available, skipping noise reduction")
            return image
        
        try:
            # Apply light Gaussian blur to reduce noise
            smoothed = cv2.GaussianBlur(image, (3, 3), 0)
            
            # Apply morphological opening to remove small noise (for grayscale images)
            if len(image.shape) == 2:  # Grayscale
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                smoothed = cv2.morphologyEx(smoothed, cv2.MORPH_OPEN, kernel)
            
            if settings.logging.ocr_per_page:
                logger.debug("✨ Applied noise reduction")
            
            return smoothed
            
        except Exception as e:
            logger.warning(f"⚠️ Noise reduction failed: {e}, using original image")
            return image
    
    def enhance_image_pipeline(
        self, 
        image: np.ndarray,
        grayscale: bool = False,
        deskew: bool = False, 
        binarize: bool = False,
        noise_reduction: bool = False
    ) -> np.ndarray:
        """
        Apply complete image enhancement pipeline based on configuration.
        
        Args:
            image: Input image array
            grayscale: Whether to convert to grayscale
            deskew: Whether to apply deskewing
            binarize: Whether to apply binarization
            noise_reduction: Whether to apply noise reduction
            
        Returns:
            Enhanced image array
        """
        result = image.copy()
        
        # Step 1: Convert to grayscale if requested
        if grayscale:
            result = self.convert_to_grayscale(result)
        
        # Step 2: Apply deskewing if enabled
        if deskew:
            result = self.apply_deskewing(result)
        
        # Step 3: Apply binarization if enabled
        if binarize:
            result = self.apply_binarization(result)
        
        # Step 4: Apply noise reduction if enabled
        if noise_reduction:
            result = self.apply_noise_reduction(result)
        
        return result
    
    def get_image_quality_metrics(self, image: np.ndarray) -> dict:
        """
        Calculate image quality metrics for preprocessing assessment.
        
        Args:
            image: Input image array
            
        Returns:
            Dictionary with quality metrics
        """
        try:
            if not HAS_CV2:
                return {'error': 'OpenCV not available for quality metrics'}
            
            # Convert to grayscale for analysis
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            else:
                gray = image
            
            # Calculate metrics
            mean_intensity = np.mean(gray)
            std_intensity = np.std(gray)
            
            # Simple sharpness measure using Laplacian variance
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            
            return {
                'mean_intensity': float(mean_intensity),
                'std_intensity': float(std_intensity),
                'sharpness_score': float(sharpness),
                'image_shape': image.shape
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Quality metrics calculation failed: {e}")
            return {'error': str(e)}






