
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/conversion_bucket.py

Bucket de conversiones por proveedor (intentado/exitoso/fallido/etc.).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from dataclasses import dataclass


@dataclass
class ConversionBucket:
    """
    Acumula intentos de pago por estado para un período/ventana.
    """
    total_attempts: int = 0
    successful: int = 0
    failed: int = 0
    pending: int = 0
    cancelled: int = 0

    def record_attempt(self, status: str) -> None:
        """
        Registra un intento de pago con el estado correspondiente.
        Acepta variantes comunes para robustez (paid/completed/succeeded, etc.).
        """
        self.total_attempts += 1
        s = (status or "").strip().lower()

        if s in {"paid", "completed", "succeeded"}:
            self.successful += 1
        elif s in {"failed", "error", "rejected"}:
            self.failed += 1
        elif s in {"pending", "created", "processing"}:
            self.pending += 1
        elif s in {"cancelled", "canceled", "expired"}:
            self.cancelled += 1

    def conversion_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return (self.successful / self.total_attempts) * 100.0

    def failure_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return (self.failed / self.total_attempts) * 100.0
# Fin del archivo backend\app\modules\payments\metrics\aggregators\conversion_bucket.py