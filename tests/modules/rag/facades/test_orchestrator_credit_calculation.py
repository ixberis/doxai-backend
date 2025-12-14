# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_orchestrator_credit_calculation.py

Tests unitarios para cálculo de créditos en orchestrator_facade.

FASE 3 - Issue #34: Test de _calculate_actual_credits

Autor: DoxAI
Fecha: 2025-11-28
"""

import pytest

from app.modules.rag.facades.orchestrator_facade import (
    _calculate_actual_credits,
    _estimate_credits,
    CreditEstimation,
)


class TestCreditEstimation:
    """Tests para estimación de créditos."""
    
    def test_estimate_credits_no_ocr(self):
        """Test estimación sin OCR."""
        estimation = _estimate_credits(
            needs_ocr=False,
            estimated_pages=0,
            estimated_chunks=20,
        )
        
        assert estimation.base_cost == 10
        assert estimation.ocr_cost == 0
        assert estimation.chunking_cost == 5
        assert estimation.embedding_cost == 40  # 2 * 20
        assert estimation.total_estimated == 55  # 10 + 0 + 5 + 40
    
    def test_estimate_credits_with_ocr(self):
        """Test estimación con OCR."""
        estimation = _estimate_credits(
            needs_ocr=True,
            estimated_pages=5,
            estimated_chunks=20,
        )
        
        assert estimation.base_cost == 10
        assert estimation.ocr_cost == 25  # 5 * 5
        assert estimation.chunking_cost == 5
        assert estimation.embedding_cost == 40  # 2 * 20
        assert estimation.total_estimated == 80  # 10 + 25 + 5 + 40
    
    def test_estimate_credits_large_document(self):
        """Test estimación para documento grande."""
        estimation = _estimate_credits(
            needs_ocr=True,
            estimated_pages=100,
            estimated_chunks=500,
        )
        
        assert estimation.base_cost == 10
        assert estimation.ocr_cost == 500  # 5 * 100
        assert estimation.chunking_cost == 5
        assert estimation.embedding_cost == 1000  # 2 * 500
        assert estimation.total_estimated == 1515  # 10 + 500 + 5 + 1000


class TestActualCreditCalculation:
    """Tests para cálculo de créditos reales (FASE 3 - Issue #34)."""
    
    def test_calculate_actual_credits_no_ocr(self):
        """Test cálculo real sin OCR."""
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=False,
            ocr_pages=0,
            total_chunks=20,
            total_embeddings=20,
        )
        
        # base + chunking + embeddings
        # 10 + 5 + (2*20) = 55
        assert credits == 55
    
    def test_calculate_actual_credits_with_ocr(self):
        """Test cálculo real con OCR."""
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=True,
            ocr_pages=5,
            total_chunks=20,
            total_embeddings=20,
        )
        
        # base + ocr + chunking + embeddings
        # 10 + (5*5) + 5 + (2*20) = 80
        assert credits == 80
    
    def test_calculate_actual_credits_large_document(self):
        """Test cálculo real para documento grande."""
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=True,
            ocr_pages=100,
            total_chunks=500,
            total_embeddings=500,
        )
        
        # base + ocr + chunking + embeddings
        # 10 + (5*100) + 5 + (2*500) = 1515
        assert credits == 1515
    
    def test_calculate_actual_credits_zero_embeddings(self):
        """Test cálculo real con cero embeddings (edge case)."""
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=False,
            ocr_pages=0,
            total_chunks=10,
            total_embeddings=0,  # Sin embeddings
        )
        
        # base + chunking (sin embeddings)
        # 10 + 5 + 0 = 15
        assert credits == 15
    
    def test_calculate_actual_credits_ocr_many_pages_few_embeddings(self):
        """Test cálculo real con muchas páginas OCR pero pocos embeddings."""
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=True,
            ocr_pages=50,
            total_chunks=100,
            total_embeddings=10,  # Pocos embeddings vs chunks
        )
        
        # base + ocr + chunking + embeddings
        # 10 + (5*50) + 5 + (2*10) = 285
        assert credits == 285
    
    def test_calculate_actual_credits_matches_formula(self):
        """Test que fórmula coincide con expectativas documentadas."""
        # Caso documentado en auditoría:
        # base=10, OCR=5 páginas, chunks=20, embeddings=20
        credits = _calculate_actual_credits(
            base_cost=10,
            ocr_executed=True,
            ocr_pages=5,
            total_chunks=20,
            total_embeddings=20,
        )
        
        expected = 10 + (5*5) + 5 + (2*20)  # 10 + 25 + 5 + 40 = 80
        assert credits == expected
        assert credits == 80


class TestCreditEstimationVsActual:
    """Tests comparando estimación vs actual."""
    
    def test_estimation_matches_actual_no_ocr(self):
        """Test que estimación coincide con cálculo real (sin OCR)."""
        estimated_chunks = 20
        
        estimation = _estimate_credits(
            needs_ocr=False,
            estimated_chunks=estimated_chunks,
        )
        
        actual = _calculate_actual_credits(
            base_cost=estimation.base_cost,
            ocr_executed=False,
            ocr_pages=0,
            total_chunks=estimated_chunks,
            total_embeddings=estimated_chunks,  # Asumiendo 1:1
        )
        
        assert actual == estimation.total_estimated
    
    def test_estimation_matches_actual_with_ocr(self):
        """Test que estimación coincide con cálculo real (con OCR)."""
        estimated_pages = 5
        estimated_chunks = 20
        
        estimation = _estimate_credits(
            needs_ocr=True,
            estimated_pages=estimated_pages,
            estimated_chunks=estimated_chunks,
        )
        
        actual = _calculate_actual_credits(
            base_cost=estimation.base_cost,
            ocr_executed=True,
            ocr_pages=estimated_pages,
            total_chunks=estimated_chunks,
            total_embeddings=estimated_chunks,  # Asumiendo 1:1
        )
        
        assert actual == estimation.total_estimated
