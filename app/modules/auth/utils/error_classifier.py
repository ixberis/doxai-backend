# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/error_classifier.py

Helper compartido para clasificación de errores de email.

Centraliza la lógica de clasificación para que ActivationFlowService
y WelcomeEmailRetryService usen la misma taxonomía de errores.

Sin PII en los valores de retorno (para uso en métricas).

Autor: Ixchel Beristain
Fecha: 2025-12-14
"""

from __future__ import annotations


def classify_email_error(error: Exception) -> str:
    """
    Clasifica un error de envío de email para métricas.
    
    Args:
        error: Excepción capturada durante el envío.
        
    Returns:
        String seguro para usar como label en métricas Prometheus.
        Valores posibles: smtp_error, template_error, timeout, 
        rate_limit, connection_error, unknown.
    """
    error_str = str(error).lower()
    
    # Timeouts (check FIRST - más específico)
    if "timeout" in error_str or "timed out" in error_str:
        return "timeout"
    
    # Rate limiting
    if "rate" in error_str and "limit" in error_str:
        return "rate_limit"
    if "throttl" in error_str:
        return "rate_limit"
    
    # Errores de autenticación SMTP (antes de smtp genérico)
    if "auth" in error_str and ("smtp" in error_str or "mail" in error_str):
        return "smtp_auth_error"
    if "authentication" in error_str and "failed" in error_str:
        return "smtp_auth_error"
    
    # Errores de conexión SMTP
    if "smtp" in error_str:
        return "smtp_error"
    
    # Errores de template/rendering
    if "template" in error_str or "render" in error_str:
        return "template_error"
    
    # DNS/resolución
    if "dns" in error_str or "resolve" in error_str or "hostname" in error_str:
        return "dns_error"
    
    # Errores de conexión genéricos (al final para no capturar timeout)
    if "connection" in error_str or "connect" in error_str:
        return "connection_error"
    
    # Default
    return "unknown"


__all__ = ["classify_email_error"]

# Fin del archivo
