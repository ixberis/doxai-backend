
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/excel_legacy_converter.py

Conversión de archivos .xls (Excel 97-2003) y .ods (OpenDocument Spreadsheet) a formato .xlsx utilizando LibreOffice en modo headless.

- Usa la CLI de LibreOffice (soffice) para convertir el archivo.
- Guarda el archivo .xlsx en el mismo directorio del original.
- Devuelve la ruta al archivo convertido o None si falla.

Requiere:
- LibreOffice instalado y disponible en el PATH del sistema.

Autor: Ixchel Beristain
Última revisión: 22/07/2025
"""

import os
import subprocess
from typing import Optional


def convert_xls_to_xlsx(xls_path: str) -> Optional[str]:
    """
    Convierte un archivo .xls o .ods a .xlsx utilizando LibreOffice en modo headless.

    Args:
        xls_path (str): Ruta del archivo .xls o .ods original

    Returns:
        str | None: Ruta al archivo .xlsx generado o None si falla
    """
    ext = os.path.splitext(xls_path)[1].lower()
    if ext not in [".xls", ".ods"]:
        return None

    output_dir = os.path.dirname(xls_path)
    base_name = os.path.splitext(os.path.basename(xls_path))[0]
    output_path = os.path.join(output_dir, base_name + ".xlsx")

    try:
        subprocess.run([
            "soffice",
            "--headless",
            "--convert-to", "xlsx",
            "--outdir", output_dir,
            xls_path
        ], check=True)

        return output_path if os.path.exists(output_path) else None

    except subprocess.CalledProcessError:
        return None
# Fin del archivo excel_legacy_converter.py







