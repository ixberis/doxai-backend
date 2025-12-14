#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script temporal para actualizar el autor en todos los docstrings del proyecto.

Reemplaza todos los patrones de autor por: "Ixchel Beristáin"
"""

import os
import re
from pathlib import Path


def update_author_in_file(file_path: Path) -> tuple[bool, str]:
    """
    Actualiza el campo Autor en un archivo Python.
    
    Returns:
        (changed, message): True si se modificó el archivo, False si no
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Patrones a reemplazar (en orden de especificidad)
        patterns = [
            (r'Autor: Ixchel Beristáin Mendoza', 'Autor: Ixchel Beristáin'),
            (r'Autor: Ixchel Beristain / ChatGPT', 'Autor: Ixchel Beristáin'),
            (r'Autor: Ixchel Beristain / DoxAI', 'Autor: Ixchel Beristáin'),
            (r'Autor: Ixchel Beristain\)', 'Autor: Ixchel Beristáin)'),
            (r'Autor: Ixchel Beristain\s+', 'Autor: Ixchel Beristáin\n'),
            (r'Autor: DoxAI', 'Autor: Ixchel Beristáin'),
            (r'Autor: AI Assistant', 'Autor: Ixchel Beristáin'),
        ]
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, f"✓ Actualizado: {file_path}"
        else:
            return False, f"  Sin cambios: {file_path}"
            
    except Exception as e:
        return False, f"✗ Error en {file_path}: {str(e)}"


def main():
    """Actualiza el autor en todos los archivos .py del proyecto."""
    backend_dir = Path(__file__).parent.parent
    
    py_files = []
    for root, dirs, files in os.walk(backend_dir):
        # Ignorar directorios de virtual environment y cache
        dirs[:] = [d for d in dirs if d not in ['.venv', 'venv', '__pycache__', '.pytest_cache', 'scripts']]
        
        for file in files:
            if file.endswith('.py'):
                py_files.append(Path(root) / file)
    
    print(f"Procesando {len(py_files)} archivos Python...")
    print("=" * 60)
    
    changed_count = 0
    unchanged_count = 0
    
    for py_file in sorted(py_files):
        changed, message = update_author_in_file(py_file)
        if changed:
            changed_count += 1
            print(message)
        else:
            unchanged_count += 1
    
    print("=" * 60)
    print(f"Resumen:")
    print(f"  Archivos modificados: {changed_count}")
    print(f"  Archivos sin cambios: {unchanged_count}")
    print(f"  Total procesado: {len(py_files)}")


if __name__ == "__main__":
    main()
