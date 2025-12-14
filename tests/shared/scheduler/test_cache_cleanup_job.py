# -*- coding: utf-8 -*-
"""
Tests para el job de limpieza de caché.

Cubre:
- Ejecución exitosa del job
- Eliminación de entradas expiradas
- Logging de estadísticas
- Manejo de errores
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from app.shared.scheduler.jobs.cache_cleanup_job import (
    cleanup_expired_cache,
    register_cache_cleanup_job
)


@pytest.mark.asyncio
async def test_cleanup_expired_cache_success():
    """
    Verifica que el job de limpieza ejecuta correctamente y retorna estadísticas.
    """
    # Mock del caché
    mock_cache = Mock()
    mock_cache.max_size = 1000
    mock_cache.cleanup.return_value = 150  # 150 entradas eliminadas
    mock_cache.get_stats.side_effect = [
        # Estadísticas antes de limpieza
        {
            'size': 950,
            'hits': 800,
            'misses': 200,
            'total': 1000,
            'hit_rate': 80.0,
            'evictions': 10
        },
        # Estadísticas después de limpieza
        {
            'size': 800,
            'hits': 800,
            'misses': 200,
            'total': 1000,
            'hit_rate': 80.0,
            'evictions': 10
        }
    ]
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        stats = await cleanup_expired_cache()
    
    # Verificar estadísticas retornadas
    assert stats['entries_before'] == 950
    assert stats['entries_after'] == 800
    assert stats['entries_removed'] == 150
    assert stats['memory_freed_kb'] == 300  # 150 * 2KB
    assert 'timestamp' in stats
    assert 'duration_ms' in stats
    assert stats['hit_rate'] == 80.0
    
    # Verificar que se llamó cleanup
    mock_cache.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired_cache_no_entries():
    """
    Verifica que el job maneja correctamente cuando no hay entradas expiradas.
    """
    mock_cache = Mock()
    mock_cache.max_size = 1000
    mock_cache.cleanup.return_value = 0  # Sin entradas eliminadas
    mock_cache.get_stats.side_effect = [
        {'size': 500, 'hits': 400, 'misses': 100, 'total': 500, 'hit_rate': 80.0, 'evictions': 5},
        {'size': 500, 'hits': 400, 'misses': 100, 'total': 500, 'hit_rate': 80.0, 'evictions': 5}
    ]
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        stats = await cleanup_expired_cache()
    
    assert stats['entries_removed'] == 0
    assert stats['memory_freed_kb'] == 0


@pytest.mark.asyncio
async def test_cleanup_expired_cache_handles_errors():
    """
    Verifica que el job maneja errores correctamente y retorna estadísticas de error.
    """
    mock_cache = Mock()
    mock_cache.max_size = 1000
    # get_stats() se llama antes de cleanup(), debe retornar datos válidos
    mock_cache.get_stats.return_value = {
        'size': 500, 'hits': 400, 'misses': 100, 'total': 500, 'hit_rate': 80.0, 'evictions': 5
    }
    mock_cache.cleanup.side_effect = RuntimeError("Cache error")
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        stats = await cleanup_expired_cache()
    
    assert 'error' in stats
    assert 'Cache error' in stats['error']
    assert stats['entries_removed'] == 0


@pytest.mark.asyncio
async def test_cleanup_logs_warning_when_cache_full():
    """
    Verifica que se registra advertencia cuando el caché está muy lleno (>90%).
    """
    mock_cache = Mock()
    mock_cache.max_size = 1000
    mock_cache.cleanup.return_value = 10
    mock_cache.get_stats.side_effect = [
        {'size': 960, 'hits': 800, 'misses': 200, 'total': 1000, 'hit_rate': 80.0, 'evictions': 10},
        {'size': 950, 'hits': 800, 'misses': 200, 'total': 1000, 'hit_rate': 80.0, 'evictions': 10}
    ]
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        with patch('app.shared.scheduler.jobs.cache_cleanup_job.logger') as mock_logger:
            stats = await cleanup_expired_cache()
            
            # Verificar que se registró advertencia
            warning_calls = [call for call in mock_logger.warning.call_args_list]
            assert any('95.0% de capacidad' in str(call) for call in warning_calls)


@pytest.mark.asyncio
async def test_cleanup_logs_warning_when_low_hit_rate():
    """
    Verifica que se registra advertencia cuando el hit rate es bajo (<60%).
    """
    mock_cache = Mock()
    mock_cache.max_size = 1000
    mock_cache.cleanup.return_value = 50
    mock_cache.get_stats.side_effect = [
        {'size': 500, 'hits': 50, 'misses': 100, 'total': 150, 'hit_rate': 33.3, 'evictions': 10},
        {'size': 450, 'hits': 50, 'misses': 100, 'total': 150, 'hit_rate': 33.3, 'evictions': 10}
    ]
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        with patch('app.shared.scheduler.jobs.cache_cleanup_job.logger') as mock_logger:
            stats = await cleanup_expired_cache()
            
            # Verificar que se registró advertencia sobre hit rate bajo
            warning_calls = [call for call in mock_logger.warning.call_args_list]
            assert any('Hit rate bajo' in str(call) for call in warning_calls)


def test_register_cache_cleanup_job():
    """
    Verifica que el job se registra correctamente en el scheduler.
    """
    mock_scheduler = Mock()
    
    job_id = register_cache_cleanup_job(mock_scheduler)
    
    assert job_id == "cache_cleanup_hourly"
    
    # Verificar que se llamó add_interval_job con parámetros correctos
    mock_scheduler.add_interval_job.assert_called_once()
    call_kwargs = mock_scheduler.add_interval_job.call_args[1]
    assert call_kwargs['job_id'] == "cache_cleanup_hourly"
    assert call_kwargs['hours'] == 1
    assert call_kwargs['minutes'] == 0
    assert call_kwargs['seconds'] == 0


@pytest.mark.asyncio
async def test_cleanup_calculates_duration():
    """
    Verifica que el job calcula correctamente la duración de ejecución.
    """
    mock_cache = Mock()
    mock_cache.max_size = 1000
    mock_cache.cleanup.return_value = 100
    mock_cache.get_stats.side_effect = [
        {'size': 800, 'hits': 400, 'misses': 100, 'total': 500, 'hit_rate': 80.0, 'evictions': 5},
        {'size': 700, 'hits': 400, 'misses': 100, 'total': 500, 'hit_rate': 80.0, 'evictions': 5}
    ]
    
    with patch('app.shared.scheduler.jobs.cache_cleanup_job.get_metadata_cache', return_value=mock_cache):
        stats = await cleanup_expired_cache()
    
    assert 'duration_ms' in stats
    assert isinstance(stats['duration_ms'], (int, float))
    assert stats['duration_ms'] >= 0


# Fin del archivo backend/tests/shared/scheduler/test_cache_cleanup_job.py
