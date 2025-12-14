
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/user_plan_enum.py

Enum de planes de usuario en el módulo Payments.
Este enum es interno del backend (no existe tipo ENUM en PostgreSQL).

Autor: Ixchel Beristain
Fecha: 20/11/2025
"""

from enum import StrEnum


class UserPlan(StrEnum):
    """Plan de suscripción o nivel de uso del usuario."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


__all__ = ["UserPlan"]

# Fin del archivo backend/app/modules/payments/enums/user_plan_enum.py








