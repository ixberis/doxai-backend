# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/json_response.py

Respuestas JSON con charset UTF-8 explícito.

Este módulo proporciona:
1. UTF8JSONResponse: Clase para usar como default_response_class en FastAPI
2. json_response_utf8: Helper funcional para casos puntuales

Uso recomendado (Opción A - default response class):
    
    from app.shared.utils.json_response import UTF8JSONResponse
    
    app = FastAPI(default_response_class=UTF8JSONResponse)
    
    # Ahora todos los return {...} automáticamente usan UTF-8
    @app.get("/test")
    def test():
        return {"message": "Éxito"}  # Content-Type: application/json; charset=utf-8

Uso alternativo (helper funcional):

    from app.shared.utils.json_response import json_response_utf8
    
    return json_response_utf8({"message": "Éxito"}, status_code=200)

Autor: DoxAI
Fecha: 2025-12-20
"""

from typing import Any, Dict, Optional
from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    """
    JSONResponse con Content-Type: application/json; charset=utf-8.
    
    Usar como default_response_class en FastAPI para que TODAS las
    respuestas JSON (return dict) incluyan charset UTF-8 automáticamente.
    
    Esto soluciona el mojibake (aÃºn → aún) cuando el cliente/proxy
    no asume UTF-8 por defecto.
    """
    media_type = "application/json; charset=utf-8"


def json_response_utf8(
    content: Any,
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> UTF8JSONResponse:
    """
    Crea un JSONResponse con Content-Type: application/json; charset=utf-8.
    
    Args:
        content: Contenido a serializar como JSON
        status_code: Código HTTP (default 200)
        headers: Headers adicionales opcionales
        
    Returns:
        UTF8JSONResponse con charset UTF-8 explícito
    """
    return UTF8JSONResponse(
        content=content,
        status_code=status_code,
        headers=headers,
    )


__all__ = ["UTF8JSONResponse", "json_response_utf8"]
