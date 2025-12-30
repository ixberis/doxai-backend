#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/fix_imports.py

Script para corregir automáticamente algunos imports rotos después
de la migración modular.

ADVERTENCIA: Este script hace cambios automáticos en el código.
Asegúrate de tener un backup o commit antes de ejecutarlo.

Uso:
    python backend/scripts/fix_imports.py --dry-run    # Ver cambios sin aplicar
    python backend/scripts/fix_imports.py              # Aplicar cambios

Autor: DoxAI
Fecha: 2025-10-18
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

class Colors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

# Mapeo de imports antiguos a nuevos (basado en auditoría real)
IMPORT_MAPPINGS = {
    # ========================================================================
    # FACADES → Services modulares (CRÍTICO)
    # ========================================================================
    r'from app\.facades\.auth_facade': 'from app.modules.auth.services.auth_service',
    r'from app\.facades\.activation_facade': 'from app.modules.auth.services.activation_service',
    r'from app\.facades\.project_facade': 'from app.modules.projects.services.project_service',
    r'from app\.facades\.file_facade': 'from app.modules.files.services.file_service',
    # (legacy payments eliminado - billing es el único módulo de pagos)
    r'from app\.facades\.download_facade': 'from app.modules.files.services.bulk_download_service',
    r'from app\.facades\.': 'from app.modules.',  # Catch-all para otros facades
    
    # ========================================================================
    # MODELS directos → Models en shared o módulos (CRÍTICO)
    # ========================================================================
    r'from app\.models\.user': 'from app.shared.models.user',
    r'from app\.models\.project': 'from app.shared.models.project',
    r'from app\.models\.input_file': 'from app.shared.models.input_file',
    r'from app\.models\.product_file': 'from app.shared.models.product_file',
    r'from app\.models\.payment': 'from app.shared.models.payment',
    r'from app\.models\.subscription': 'from app.shared.models.subscription',
    r'from app\.models\.billing': 'from app.shared.models.billing',
    r'from app\.models\.': 'from app.shared.models.',  # Catch-all para otros models
    
    # ========================================================================
    # SCHEMAS directos → Schemas en módulos (CRÍTICO)
    # ========================================================================
    r'from app\.schemas\.download_schemas': 'from app.modules.files.schemas.download_schemas',
    r'from app\.schemas\.auth': 'from app.modules.auth.schemas',
    r'from app\.schemas\.project': 'from app.modules.projects.schemas',
    r'from app\.schemas\.file': 'from app.modules.files.schemas',
    # (legacy payments schemas eliminado - usar billing.schemas)
    r'from app\.schemas\.': 'from app.modules.',  # Catch-all
    
    # ========================================================================
    # SERVICES directos → Services en shared o módulos (ADVERTENCIA)
    # ========================================================================
    r'from app\.services\.email_service': 'from app.shared.services.email_service',
    r'from app\.services\.storage_service': 'from app.shared.services.storage_service',
    r'from app\.services\.security': 'from app.shared.utils.security',
    r'from app\.services\.validation': 'from app.shared.utils.validation',
    r'from app\.services\.logger': 'from app.shared.utils.logger',
    
    # ========================================================================
    # REPOSITORIES → Models con métodos de clase (CRÍTICO)
    # ========================================================================
    r'from app\.repositories\.user_repository': 'from app.shared.models.user',
    r'from app\.repositories\.project_repository': 'from app.shared.models.project',
    r'from app\.repositories\.': 'from app.shared.models.',
    
    # ========================================================================
    # ENUMS directos → Shared enums (ADVERTENCIA)
    # ========================================================================
    r'from app\.enums\.': 'from app.shared.enums.',
    
    # ========================================================================
    # CONFIG y DATABASE (ya tienen wrappers)
    # ========================================================================
    r'from app\.config\.config_settings import get_settings': 'from app.shared.config import get_settings',
    r'from app\.config import settings': 'from app.shared.config import settings',
    r'from app\.db\.session': 'from app.shared.database',
    r'from app\.db import Base': 'from app.shared.database import Base',
}

def find_python_files(root_path: Path, exclude_dirs: List[str] = None) -> List[Path]:
    """Encuentra todos los archivos .py, excluyendo ciertos directorios."""
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', 'venv', '.git', 'node_modules', 'tests']
    
    python_files = []
    for py_file in root_path.rglob("*.py"):
        # Verificar si el archivo está en un directorio excluido
        if not any(excluded in py_file.parts for excluded in exclude_dirs):
            python_files.append(py_file)
    
    return python_files

def fix_imports_in_file(file_path: Path, mappings: Dict[str, str], dry_run: bool = True) -> Tuple[bool, int]:
    """
    Corrige los imports en un archivo.
    
    Returns:
        (modified, num_changes)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            original_content = content
        
        changes = 0
        for old_pattern, new_import in mappings.items():
            content, count = re.subn(old_pattern, new_import, content)
            changes += count
        
        if changes > 0 and not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, changes
        
        return changes > 0, changes
        
    except Exception as e:
        print(f"{Colors.RED}Error procesando {file_path}: {e}{Colors.END}")
        return False, 0

def main():
    parser = argparse.ArgumentParser(description='Corregir imports rotos después de migración modular')
    parser.add_argument('--dry-run', action='store_true', help='Mostrar cambios sin aplicarlos')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar detalles de cada cambio')
    args = parser.parse_args()
    
    # Determinar directorios
    script_dir = Path(__file__).parent
    backend_root = script_dir.parent
    app_root = backend_root / "app"
    
    print(f"{Colors.BOLD}🔧 Corrector Automático de Imports - Backend DoxAI{Colors.END}")
    
    if args.dry_run:
        print(f"{Colors.YELLOW}Modo DRY-RUN: No se aplicarán cambios{Colors.END}")
    else:
        print(f"{Colors.RED}ADVERTENCIA: Se modificarán archivos. Asegúrate de tener un backup.{Colors.END}")
        response = input(f"¿Continuar? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Operación cancelada")
            return 0
    
    print(f"\nEscaneando: {app_root}\n")
    
    # Buscar archivos Python
    py_files = find_python_files(app_root)
    print(f"📁 Archivos Python encontrados: {len(py_files)}\n")
    
    # Procesar archivos
    files_modified = 0
    total_changes = 0
    
    for py_file in py_files:
        modified, changes = fix_imports_in_file(py_file, IMPORT_MAPPINGS, dry_run=args.dry_run)
        
        if modified:
            files_modified += 1
            total_changes += changes
            rel_path = py_file.relative_to(backend_root)
            
            if args.verbose:
                print(f"{Colors.GREEN}✓{Colors.END} {rel_path} ({changes} cambios)")
    
    # Resumen
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}RESUMEN{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    if args.dry_run:
        print(f"{Colors.YELLOW}Modo DRY-RUN activado{Colors.END}")
    
    print(f"Archivos que serían modificados: {Colors.BOLD}{files_modified}{Colors.END}")
    print(f"Total de cambios de imports: {Colors.BOLD}{total_changes}{Colors.END}\n")
    
    if files_modified > 0:
        if args.dry_run:
            print(f"{Colors.YELLOW}Para aplicar cambios, ejecuta sin --dry-run:{Colors.END}")
            print(f"  python backend/scripts/fix_imports.py")
        else:
            print(f"{Colors.GREEN}✅ Cambios aplicados exitosamente{Colors.END}")
            print(f"\n{Colors.BOLD}SIGUIENTE PASO:{Colors.END}")
            print(f"  1. Revisar los cambios con git diff")
            print(f"  2. Ejecutar los tests para verificar")
            print(f"  3. Corregir manualmente imports que requieran lógica compleja (facades)")
    else:
        print(f"{Colors.GREEN}No se encontraron imports para corregir{Colors.END}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
