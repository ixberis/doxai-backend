# -*- coding: utf-8 -*-
"""
Optimization Recommender - Generates processing optimization recommendations.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path

from app.shared.enums.ocr_optimization_enum import ProcessingMode
from .pdf_complexity_analyzer import PDFComplexityAnalyzer

logger = logging.getLogger(__name__)


class OptimizationRecommender:
    """Generates optimization recommendations for PDF processing."""
    
    def __init__(self):
        self.complexity_analyzer = PDFComplexityAnalyzer()
    
    def get_optimization_recommendations(
        self, 
        pdf_path: Path,
        fast_elements: Optional[List] = None
    ) -> Dict[str, Any]:
        """Provides optimization recommendations for a PDF."""
        analysis = self.complexity_analyzer.analyze_pdf_complexity(pdf_path, fast_elements)
        
        recommendations = {
            'processing_mode': ProcessingMode.FAST,
            'expected_time_range': '5-10 seconds',
            'memory_usage': 'Low',
            'quality_tradeoffs': [],
            'optimization_tips': []
        }
        
        complexity = analysis['complexity_score']
        
        if complexity <= 3:
            recommendations['processing_mode'] = ProcessingMode.FAST
            recommendations['optimization_tips'].append(
                "Simple document, fast processing recommended"
            )
        elif complexity >= 7:
            recommendations['processing_mode'] = ProcessingMode.SELECTIVE
            recommendations['expected_time_range'] = '30-60 seconds'
            recommendations['memory_usage'] = 'High'
            recommendations['quality_tradeoffs'].append(
                "Longer processing time for better quality"
            )
        else:
            recommendations['processing_mode'] = ProcessingMode.HYBRID
            recommendations['expected_time_range'] = '15-30 seconds'
            recommendations['memory_usage'] = 'Medium'
        
        return recommendations






