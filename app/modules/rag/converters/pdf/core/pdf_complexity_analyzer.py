# -*- coding: utf-8 -*-
"""
PDF Complexity Analyzer - Analyzes PDF characteristics to determine processing complexity.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path

from ..utils.table_detection import detect_table_pages

logger = logging.getLogger(__name__)


class PDFComplexityAnalyzer:
    """Analyzes PDF complexity to guide processing strategy selection."""
    
    def analyze_pdf_complexity(
        self,
        pdf_path: Path,
        fast_elements: Optional[List] = None,
        pdf_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyzes PDF complexity for optimal strategy determination."""
        analysis = {
            'total_pages': 0,
            'estimated_table_pages': 0,
            'text_heavy_pages': 0,
            'image_heavy_pages': 0,
            'complexity_score': 0,
            'has_complex_layouts': False,
            'estimated_processing_time': 0
        }
        
        try:
            # Get basic PDF info
            from .pdf_utils import get_pdf_page_count
            analysis['total_pages'] = get_pdf_page_count(pdf_path)
            
            if fast_elements:
                # Analysis based on fast elements
                table_pages = detect_table_pages(fast_elements)
                analysis['estimated_table_pages'] = len(table_pages)
                
                # Content type analysis
                content_analysis = self._analyze_content_types(fast_elements)
                analysis.update(content_analysis)
            
            # Calculate complexity score
            analysis['complexity_score'] = self._calculate_complexity_score(analysis)
            
            # Estimate processing time
            analysis['estimated_processing_time'] = self._estimate_processing_time(analysis)
            
            logger.debug(f"📊 Complexity analysis: {analysis}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Error in complexity analysis: {e}")
            # Conservative default values
            analysis['complexity_score'] = 5  # Medium
            analysis['estimated_processing_time'] = 30
            return analysis
    
    def _analyze_content_types(self, elements: List) -> Dict[str, Any]:
        """Analyzes content types in elements."""
        analysis = {
            'text_heavy_pages': 0,
            'image_heavy_pages': 0,
            'has_complex_layouts': False
        }
        
        try:
            page_content = {}
            
            for element in elements:
                page_num = getattr(element, 'metadata', {}).get('page_number', 1)
                if page_num not in page_content:
                    page_content[page_num] = {'text_length': 0, 'image_count': 0}
                
                # Analyze text content
                text = getattr(element, 'text', '') or ''
                page_content[page_num]['text_length'] += len(text)
                
                # Detect images/figures
                category = getattr(element, 'category', '')
                if category in ['Image', 'Figure']:
                    page_content[page_num]['image_count'] += 1
            
            # Classify pages
            for page_data in page_content.values():
                if page_data['text_length'] > 2000:  # Heavy text
                    analysis['text_heavy_pages'] += 1
                if page_data['image_count'] > 2:  # Many images
                    analysis['image_heavy_pages'] += 1
            
            # Detect complex layouts
            if analysis['image_heavy_pages'] > 0 or analysis['text_heavy_pages'] > 3:
                analysis['has_complex_layouts'] = True
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Error analyzing content types: {e}")
            return analysis
    
    def _calculate_complexity_score(self, analysis: Dict[str, Any]) -> int:
        """Calculates complexity score (1-10)."""
        score = 1
        
        # Total pages
        if analysis['total_pages'] > 10:
            score += 2
        elif analysis['total_pages'] > 5:
            score += 1
        
        # Table presence
        if analysis['estimated_table_pages'] > 0:
            score += 2
        
        # Complex content
        if analysis['has_complex_layouts']:
            score += 2
        
        # Heavy content pages
        if analysis['text_heavy_pages'] > 2:
            score += 1
        if analysis['image_heavy_pages'] > 1:
            score += 1
        
        return min(score, 10)  # Maximum 10
    
    def _estimate_processing_time(self, analysis: Dict[str, Any]) -> int:
        """Estimates processing time in seconds."""
        base_time_per_page = 2  # base seconds per page
        
        total_pages = analysis['total_pages']
        table_pages = analysis['estimated_table_pages']
        complexity = analysis['complexity_score']
        
        # Base time
        estimated_time = total_pages * base_time_per_page
        
        # Complexity adjustment
        complexity_multiplier = 1 + (complexity / 10)
        estimated_time *= complexity_multiplier
        
        # Additional time for tables
        estimated_time += table_pages * 5  # 5 extra seconds per table
        
        return int(estimated_time)






