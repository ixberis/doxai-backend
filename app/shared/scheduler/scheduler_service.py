# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/scheduler_service.py

Servicio de programación de tareas periódicas usando APScheduler.

Autor: DoxAI
Fecha: 2025-11-05
"""

import logging
from typing import Optional, Callable, Any
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Servicio de programación de tareas periódicas.
    
    Funcionalidades:
    - Configuración de jobs con intervalos o expresiones cron
    - Registro y eliminación dinámica de jobs
    - Logging de ejecuciones
    - Manejo de errores y reintentos
    """
    
    def __init__(self):
        """Inicializa el scheduler con configuración por defecto."""
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # Combinar ejecuciones perdidas
            'max_instances': 1,  # Una instancia por job
            'misfire_grace_time': 30  # Tolerar 30s de retraso
        }
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        self._started = False
        logger.info("SchedulerService inicializado")
    
    def start(self):
        """Inicia el scheduler."""
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("SchedulerService iniciado")
    
    def shutdown(self, wait: bool = True):
        """
        Detiene el scheduler.
        
        Args:
            wait: Si True, espera a que terminen los jobs en ejecución
        """
        if self._started:
            self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("SchedulerService detenido")
    
    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        **kwargs
    ) -> str:
        """
        Agrega un job que se ejecuta a intervalos regulares.
        
        Args:
            func: Función a ejecutar
            job_id: ID único del job
            hours: Intervalo en horas
            minutes: Intervalo en minutos
            seconds: Intervalo en segundos
            **kwargs: Argumentos adicionales para func
        
        Returns:
            ID del job agregado
        """
        trigger = IntervalTrigger(
            hours=hours,
            minutes=minutes,
            seconds=seconds
        )
        
        self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            replace_existing=True,
            kwargs=kwargs
        )
        
        logger.info(
            f"Job '{job_id}' agregado: cada {hours}h {minutes}m {seconds}s"
        )
        return job_id
    
    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        cron_expression: str = None,
        hour: str = None,
        minute: str = None,
        **kwargs
    ) -> str:
        """
        Agrega un job que se ejecuta según expresión cron.
        
        Args:
            func: Función a ejecutar
            job_id: ID único del job
            cron_expression: Expresión cron completa (5 campos)
            hour: Hora de ejecución (formato cron)
            minute: Minuto de ejecución (formato cron)
            **kwargs: Argumentos adicionales para func
        
        Returns:
            ID del job agregado
        """
        if cron_expression:
            # Parsear expresión cron
            parts = cron_expression.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                )
            else:
                raise ValueError("Expresión cron inválida (requiere 5 campos)")
        else:
            trigger = CronTrigger(hour=hour, minute=minute)
        
        self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            replace_existing=True,
            kwargs=kwargs
        )
        
        logger.info(f"Job '{job_id}' agregado: expresión cron")
        return job_id
    
    def remove_job(self, job_id: str) -> bool:
        """
        Elimina un job programado.
        
        Args:
            job_id: ID del job a eliminar
        
        Returns:
            True si se eliminó, False si no existía
        """
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Job '{job_id}' eliminado")
            return True
        except Exception as e:
            logger.warning(f"No se pudo eliminar job '{job_id}': {e}")
            return False
    
    def get_jobs(self) -> list:
        """
        Obtiene lista de jobs programados.
        
        Returns:
            Lista de jobs con información básica
        """
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Obtiene estado de un job específico.
        
        Args:
            job_id: ID del job
        
        Returns:
            Dict con información del job o None si no existe
        """
        job = self._scheduler.get_job(job_id)
        if job:
            return {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time,
                'trigger': str(job.trigger),
                'pending': job.pending
            }
        return None
    
    @property
    def is_running(self) -> bool:
        """Retorna True si el scheduler está activo."""
        return self._started and self._scheduler.running


# Singleton global del scheduler
_scheduler_instance: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """
    Obtiene la instancia global del scheduler (singleton).
    
    Returns:
        Instancia de SchedulerService
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SchedulerService()
    return _scheduler_instance


# Fin del archivo backend/app/shared/scheduler/scheduler_service.py
