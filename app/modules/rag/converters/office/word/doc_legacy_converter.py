
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/doc_legacy_converter.py

Conversión de archivos .doc (Microsoft Word 97-2003) y .odt (OpenDocument Text) a formato .docx mediante LibreOffice.

- Utiliza la interfaz de línea de comandos de LibreOffice (soffice) en modo headless.
- Guarda el archivo convertido en el mismo directorio del original.
- Retorna la ruta del archivo .docx generado para su posterior procesamiento.

Requiere:
- LibreOffice instalado y agregado al PATH del sistema (comando `soffice` disponible).

Autor: Ixchel Beristain
Última revisión: 22/07/2025
"""

import os
import subprocess
from typing import Optional


def convert_doc_to_docx(doc_path: str) -> Optional[str]:
    """
    Convierte un archivo .doc o .odt a .docx utilizando LibreOffice en modo headless.

    Args:
        doc_path (str): Ruta del archivo original (.doc o .odt)

    Returns:
        str | None: Ruta al archivo .docx generado, o None si la conversión falla
    """
    ext = os.path.splitext(doc_path)[1].lower()
    if ext not in [".doc", ".odt"]:
        return None

    output_dir = os.path.dirname(doc_path)
    base_name = os.path.splitext(os.path.basename(doc_path))[0]
    output_path = os.path.join(output_dir, base_name + ".docx")

    try:
        subprocess.run([
            "soffice",
            "--headless",
            "--convert-to", "docx",
            "--outdir", output_dir,
            doc_path
        ], check=True)

        return output_path if os.path.exists(output_path) else None

    except subprocess.CalledProcessError:
        return None
# Fin del archivo doc_legacy_converter.py







