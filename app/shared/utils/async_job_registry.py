# -*- coding: utf-8 -*-
"""
backend/app/utils/async_job_registry.py

Registry global para mantener referencias de asyncio.Task activos.
Permite cancelación ordenada durante shutdown y previene memory leaks.

Autor: Migración a asyncio tasks
Fecha: 09/09/2025
"""

import asyncio
import logging
import threading
from typing import Dict, Set, Optional
from weakref import WeakSet

logger = logging.getLogger(__name__)

class AsyncJobRegistry:
    """Registry thread-safe para mantener referencias de asyncio.Task activos."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._weak_tasks: WeakSet[asyncio.Task] = WeakSet()
    
    def register_task(self, job_id: str, task: asyncio.Task) -> None:
        """Registra una task activa por job_id."""
        with self._lock:
            self._active_tasks[job_id] = task
            self._weak_tasks.add(task)
            logger.debug(f"📝 Task registrada: job_id={job_id}, task_id={id(task)}")
    
    def unregister_task(self, job_id: str) -> None:
        """Desregistra una task por job_id."""
        with self._lock:
            task = self._active_tasks.pop(job_id, None)
            if task:
                logger.debug(f"🗑️ Task desregistrada: job_id={job_id}, task_id={id(task)}")
    
    def get_task(self, job_id: str) -> Optional[asyncio.Task]:
        """Obtiene la task activa por job_id."""
        with self._lock:
            return self._active_tasks.get(job_id)
    
    def cancel_task(self, job_id: str) -> bool:
        """Cancela una task específica por job_id."""
        with self._lock:
            task = self._active_tasks.get(job_id)
            if task and not task.done():
                task.cancel()
                logger.info(f"❌ Task cancelada: job_id={job_id}")
                return True
            return False
    
    def get_active_count(self) -> int:
        """Retorna el número de tasks activas."""
        with self._lock:
            return len([t for t in self._active_tasks.values() if not t.done()])
    
    async def cancel_all_tasks(self, timeout: float = 30.0) -> None:
        """
        Cancela todas las tasks activas y espera a que terminen.
        
        Args:
            timeout: Tiempo máximo de espera en segundos
        """
        with self._lock:
            active_tasks = list(self._active_tasks.values())
            active_count = len([t for t in active_tasks if not t.done()])
        
        if active_count == 0:
            logger.info("🟢 No hay tasks activas para cancelar")
            return
        
        logger.info(f"🔄 Cancelando {active_count} tasks activas...")
        
        # Cancelar todas las tasks
        for task in active_tasks:
            if not task.done():
                task.cancel()
        
        # Esperar a que terminen con timeout
        if active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*active_tasks, return_exceptions=True),
                    timeout=timeout
                )
                logger.info("✅ Todas las tasks canceladas exitosamente")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Timeout esperando cancelación de tasks ({timeout}s)")
            except Exception as e:
                logger.error(f"❌ Error durante cancelación de tasks: {e}")
        
        # Limpiar registry
        with self._lock:
            self._active_tasks.clear()

# Instance global
job_registry = AsyncJobRegistry()






