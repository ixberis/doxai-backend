
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/login_attempt_service.py

Servicio de rate limiting para intentos de login.
Implementa control de intentos fallidos por IP y por email.

Autor: DoxAI
Fecha: 02/11/2025
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from app.shared.config.config_loader import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AttemptRecord:
    """Registro de intentos de login"""
    count: int = 0
    first_attempt: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_attempt: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    locked_until: Optional[datetime] = None


class LoginAttemptService:
    """
    Servicio de rate limiting en memoria para intentos de login.
    
    Configuración desde settings:
    - LOGIN_ATTEMPTS_LIMIT: máximo de intentos en ventana de tiempo
    - LOGIN_ATTEMPTS_TIME_WINDOW_MINUTES: ventana de tiempo en minutos
    - LOGIN_LOCKOUT_DURATION_MINUTES: duración del bloqueo tras exceder límite
    
    Notas:
    - Implementación stateless en memoria (se reinicia con el proceso)
    - Para producción se recomienda usar Redis para persistencia distribuida
    """
    
    # Instancia global opcional para reutilizar el mismo rate limiter en memoria
    _default_instance: "LoginAttemptService" | None = None

    @classmethod
    def get_default_instance(cls) -> "LoginAttemptService":
        """
        Devuelve una instancia global en memoria del servicio.

        Notas:
            - Útil para aplicar límites de intentos a nivel de proceso.
            - Para pruebas unitarias se puede instanciar la clase directamente
              sin usar este método.
        """
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance
    
    def __init__(self):
        self.settings = get_settings()
        self.max_attempts = int(getattr(self.settings, 'login_attempts_limit', 5))
        self.time_window_minutes = int(getattr(self.settings, 'login_attempts_time_window_minutes', 15))
        self.lockout_duration_minutes = int(getattr(self.settings, 'login_lockout_duration_minutes', 30))
        
        # Storage en memoria: {identifier: AttemptRecord}
        self._attempts_by_ip: dict[str, AttemptRecord] = defaultdict(AttemptRecord)
        self._attempts_by_email: dict[str, AttemptRecord] = defaultdict(AttemptRecord)
        
        logger.info(
            f"LoginAttemptService inicializado: max_attempts={self.max_attempts}, "
            f"window={self.time_window_minutes}min, lockout={self.lockout_duration_minutes}min"
        )
    
    def _is_locked(self, record: AttemptRecord) -> bool:
        if record.locked_until is None:
            return False
        now = datetime.now(timezone.utc)
        return now < record.locked_until
    
    def _reset_if_expired(self, record: AttemptRecord) -> None:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.time_window_minutes)
        
        if record.first_attempt < window_start:
            record.count = 0
            record.first_attempt = now
            record.last_attempt = now
            record.locked_until = None
    
    def check_rate_limit(self, identifier: str, identifier_type: str = "ip") -> None:
        """
        Verifica si el identificador ha excedido el límite de intentos.
        
        Args:
            identifier: IP o email del cliente
            identifier_type: "ip" o "email"
            
        Raises:
            HTTPException 429: Si se excedió el límite de intentos
        """
        storage = self._attempts_by_ip if identifier_type == "ip" else self._attempts_by_email
        record = storage[identifier]
        
        # Verificar si está bloqueado
        if self._is_locked(record):
            logger.warning(f"Intentos de login bloqueados para {identifier}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos de inicio de sesión. Intente más tarde.",
            )
        
        # Resetear si expiró la ventana
        self._reset_if_expired(record)
    
    def record_failed_attempt(self, ip: str, email: str) -> None:
        """
        Registra un intento de login fallido.
        
        Args:
            ip: Dirección IP del cliente
            email: Email del usuario que intentó autenticarse
        """
        now = datetime.now(timezone.utc)
        
        for identifier, storage in [(ip, self._attempts_by_ip), (email, self._attempts_by_email)]:
            record = storage[identifier]
            self._reset_if_expired(record)
            
            record.count += 1
            record.last_attempt = now
            
            # Si excedió el límite, bloquear
            if record.count >= self.max_attempts:
                record.locked_until = now + timedelta(minutes=self.lockout_duration_minutes)
                logger.warning(
                    f"Límite de intentos excedido para {identifier}, "
                    f"bloqueado hasta {record.locked_until.isoformat()}"
                )
    
    def record_successful_login(self, ip: str, email: str) -> None:
        """
        Resetea el contador de intentos tras un login exitoso.
        
        Args:
            ip: Dirección IP del cliente
            email: Email del usuario autenticado
        """
        now = datetime.now(timezone.utc)
        
        for identifier, storage in [(ip, self._attempts_by_ip), (email, self._attempts_by_email)]:
            if identifier in storage:
                record = storage[identifier]
                record.count = 0
                record.first_attempt = now
                record.last_attempt = now
                record.locked_until = None
    
    def get_attempts(self, identifier: str, identifier_type: str = "ip") -> AttemptRecord:
        """
        Devuelve el registro de intentos para un identificador.
        
        Args:
            identifier: IP o email
            identifier_type: "ip" o "email"
            
        Returns:
            AttemptRecord con el estado actual
        """
        storage = self._attempts_by_ip if identifier_type == "ip" else self._attempts_by_email
        record = storage[identifier]
        self._reset_if_expired(record)
        return record
    
    def remaining_attempts(self, identifier: str, identifier_type: str = "ip") -> int:
        """
        Calcula cuántos intentos restantes tiene el identificador.
        
        Args:
            identifier: IP o email
            identifier_type: "ip" o "email"
            
        Returns:
            Número de intentos restantes
        """
        storage = self._attempts_by_ip if identifier_type == "ip" else self._attempts_by_email
        record = storage[identifier]
        
        if self._is_locked(record):
            return 0
        
        self._reset_if_expired(record)
        return max(0, self.max_attempts - record.count)


__all__ = ["LoginAttemptService"]

# Fin del script backend/app/modules/auth/services/login_attempt_service.py