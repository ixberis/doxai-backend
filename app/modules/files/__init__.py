
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/__init__.py

Módulo de gestión de archivos de DoxAI.

Responsabilidades (alto nivel):
- Gestión de archivos de entrada (insumos) y salida (productos).
- Metadatos de procesamiento y almacenamiento.
- Orquestación de conversiones y análisis documental.
- Integración con servicios de métricas (expuestos en subpaquetes).

Notas de diseño:
- Este paquete debe permanecer liviano: NO importes models/schemas/services aquí
  para evitar ciclos de importación y mejorar tiempos de carga en tests.
- Exportamos únicamente 'enums' a nivel de paquete como superficie pública estable.

Autor: DoxAI
Fecha: 2025-11-10
"""

# Superficie pública mínima y estable
from . import enums as enums  # noqa: F401
from . import routes as routes  # noqa: F401

# Importar get_files_routers para compatibilidad con app.main
from .routes import get_files_routers

__all__ = ["enums", "routes", "get_files_routers"]

# Fin del archivo backend/app/modules/files/__init__.py
