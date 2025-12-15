# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/collectors/welcome_email_collectors.py

Coleccionistas Prometheus para métricas de Welcome Email.

Define contadores para:
- Correos de bienvenida enviados/fallidos
- Claims atómicos (anti-race)
- Reintentos automáticos

Autor: Ixchel Beristain
Fecha: 2025-12-14
"""
from prometheus_client import Counter

NAMESPACE = "doxai"
SUBSYSTEM = "auth"

# Contador de correos enviados exitosamente
welcome_email_sent_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_welcome_email_sent_total",
    "Welcome emails sent successfully",
    labelnames=("provider",),
)

# Contador de correos fallidos
welcome_email_failed_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_welcome_email_failed_total",
    "Welcome emails that failed to send",
    labelnames=("provider", "reason"),
)

# Contador de claims exitosos (anti-race)
welcome_email_claimed_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_welcome_email_claimed_total",
    "Welcome email claims (anti-race condition protection)",
)

# Contador de reintentos automáticos
welcome_email_retry_total = Counter(
    f"{NAMESPACE}_{SUBSYSTEM}_welcome_email_retry_total",
    "Welcome email retry outcomes",
    labelnames=("outcome",),  # sent|failed|skipped
)

__all__ = [
    "welcome_email_sent_total",
    "welcome_email_failed_total",
    "welcome_email_claimed_total",
    "welcome_email_retry_total",
]

# Fin del archivo
