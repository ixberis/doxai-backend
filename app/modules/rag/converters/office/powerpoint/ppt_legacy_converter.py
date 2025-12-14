
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/ppt_legacy_converter.py

Conversión de archivos .ppt (PowerPoint 97-2003) y .odp (OpenDocument Presentation) a formato .pptx mediante LibreOffice en modo headless.

- Utiliza la interfaz CLI de LibreOffice (soffice) para convertir el archivo.
- El archivo convertido se guarda en el mismo directorio que el original.
- Devuelve la ruta del archivo .pptx generado o None si la conversión falla.

Requiere:
- LibreOffice instalado y accesible desde el sistema (comando `soffice`).

Autor: Ixchel Beristain
Última revisión: 22/07/2025
"""

import os
import subprocess
from typing import Optional


def convert_ppt_to_pptx(ppt_path: str) -> Optional[str]:
    """
    Convierte un archivo .ppt o .odp a .pptx utilizando LibreOffice en modo headless.

    Args:
        ppt_path (str): Ruta absoluta del archivo original (.ppt o .odp)

    Returns:
        str | None: Ruta al nuevo archivo .pptx, o None si falla
    """
    ext = os.path.splitext(ppt_path)[1].lower()
    if ext not in [".ppt", ".odp"]:
        return None

    output_dir = os.path.dirname(ppt_path)
    base_name = os.path.splitext(os.path.basename(ppt_path))[0]
    output_path = os.path.join(output_dir, base_name + ".pptx")

    try:
        subprocess.run([
            "soffice",
            "--headless",
            "--convert-to", "pptx",
            "--outdir", output_dir,
            ppt_path
        ], check=True)

        return output_path if os.path.exists(output_path) else None

    except subprocess.CalledProcessError:
        return None
# Fin del archivo ppt_legacy_converter.py






