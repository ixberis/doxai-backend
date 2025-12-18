# -*- coding: utf-8 -*-
"""
backend/app/shared/http_utils/__init__.py

Helpers HTTP reutilizables.
"""

from app.shared.http_utils.request_meta import (
    get_client_ip,
    get_user_agent,
    get_request_meta,
)

__all__ = [
    "get_client_ip",
    "get_user_agent",
    "get_request_meta",
]
