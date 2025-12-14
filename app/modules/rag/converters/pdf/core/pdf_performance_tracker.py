# -*- coding: utf-8 -*-
"""
Performance Tracker - Tracks and manages processing performance history.
"""

from __future__ import annotations
from typing import Dict, Any
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Tracks performance metrics for processing optimization."""
    
    def __init__(self):
        self.performance_history = {}
    
    def update_performance_history(
        self, 
        pdf_path: Path, 
        strategy: Dict[str, Any], 
        processing_time: float
    ):
        """Updates performance history for future optimizations."""
        try:
            file_size = pdf_path.stat().st_size
            
            self.performance_history[str(pdf_path)] = {
                'strategy': strategy,
                'processing_time': processing_time,
                'file_size': file_size,
                'timestamp': time.time()
            }
            
            # Keep only last 100 records
            if len(self.performance_history) > 100:
                oldest_key = min(
                    self.performance_history.keys(),
                    key=lambda k: self.performance_history[k]['timestamp']
                )
                del self.performance_history[oldest_key]
                
        except Exception as e:
            logger.error(f"❌ Error updating history: {e}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Returns performance statistics."""
        if not self.performance_history:
            return {'total_processed': 0, 'average_time': 0}
        
        times = [entry['processing_time'] for entry in self.performance_history.values()]
        
        return {
            'total_processed': len(self.performance_history),
            'average_time': sum(times) / len(times),
            'min_time': min(times),
            'max_time': max(times)
        }






