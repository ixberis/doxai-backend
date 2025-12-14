
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/collectors/auth_collectors.py

Coleccionistas Prometheus para el módulo Auth de DoxAI.

Define contadores, gauges e histogramas para registrar:
- Registros de usuarios
- Activaciones de cuenta
- Intentos de login (éxito/falla)
- Resets de contraseña
- Sesiones activas
- Latencias de login

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from prometheus_client import Counter, Gauge, Histogram

NAMESPACE = "doxai"
SUBSYSTEM = "auth"

auth_registrations_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_registrations_total",
    "Total de registros de usuarios",
)

auth_activations_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_activations_total",
    "Total de activaciones de cuenta",
)

auth_activation_conversion_ratio = Gauge(
    f"{NAMESPACE}_{SUBSYSTEM}_activation_conversion_ratio",
    "Ratio de conversión registro→activación (0..1) (gauge derivado)",
)

auth_login_attempts_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_login_attempts_total",
    "Intentos de login por etiqueta",
    labelnames=("success", "reason"),
)

auth_password_resets_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_password_resets_total",
    "Resets de password por estado",
    labelnames=("status",),  # requested|completed
)

auth_active_sessions = Gauge(
    f"{NAMESPACE}_{SUBSYSTEM}_active_sessions",
    "Sesiones activas (no revocadas y no expiradas)",
)

auth_login_latency_seconds = Histogram(
    f"{NAMESPACE}_{SUBSYSTEM}_login_latency_seconds",
    "Latencia de login (segundos) P50/P90/P99",
)

__all__ = [
    "auth_registrations_total",
    "auth_activations_total",
    "auth_activation_conversion_ratio",
    "auth_login_attempts_total",
    "auth_password_resets_total",
    "auth_active_sessions",
    "auth_login_latency_seconds",
]

# Fin del archivo backend/app/modules/auth/metrics/collectors/auth_collectors.py
