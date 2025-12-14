#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/audit_imports.py

Script de auditoría automática para detectar imports rotos y problemas
en la estructura del backend después de la migración modular.

Uso:
    python backend/scripts/audit_imports.py

Autor: DoxAI
Fecha: 2025-10-18
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

# Colores para terminal
class Colors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def find_python_files(root_path: Path) -> List[Path]:
    """Encuentra todos los archivos .py en el directorio."""
    return list(root_path.rglob("*.py"))

def check_imports(file_path: Path, patterns: Dict[str, re.Pattern]) -> Dict[str, List[Tuple[int, str]]]:
    """
    Revisa un archivo en busca de imports problemáticos.
    
    Returns:
        Dict con categorías de problemas y lista de (línea, código)
    """
    issues = defaultdict(list)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                for category, pattern in patterns.items():
                    if pattern.search(line):
                        issues[category].append((line_num, line))
    except Exception as e:
        issues['read_error'].append((0, str(e)))
    
    return issues

def main():
    # Determinar el directorio raíz del backend
    script_dir = Path(__file__).parent
    backend_root = script_dir.parent
    app_root = backend_root / "app"
    
    print(f"{Colors.BOLD}🔍 Auditoría de Imports - Backend DoxAI{Colors.END}")
    print(f"Escaneando: {app_root}\n")
    
    # Patrones de imports problemáticos
    patterns = {
        'facades': re.compile(r'from\s+app\.facades\.'),
        'services_direct': re.compile(r'from\s+app\.services\.'),
        'models_direct': re.compile(r'from\s+app\.models\.'),
        'schemas_direct': re.compile(r'from\s+app\.schemas\.'),
        'routes_direct': re.compile(r'from\s+app\.routes\.'),
        'repositories': re.compile(r'from\s+app\.repositories\.'),
        'enums_direct': re.compile(r'from\s+app\.enums\.'),
    }
    
    # Buscar todos los archivos Python
    py_files = find_python_files(app_root)
    
    print(f"📁 Archivos Python encontrados: {len(py_files)}\n")
    
    # Estadísticas globales
    total_issues = defaultdict(int)
    files_with_issues = defaultdict(set)
    
    # Analizar cada archivo
    detailed_issues = defaultdict(lambda: defaultdict(list))
    
    for py_file in py_files:
        issues = check_imports(py_file, patterns)
        
        if issues:
            rel_path = py_file.relative_to(backend_root)
            
            for category, occurrences in issues.items():
                total_issues[category] += len(occurrences)
                files_with_issues[category].add(str(rel_path))
                detailed_issues[category][str(rel_path)] = occurrences
    
    # Reportar resultados
    print(f"{Colors.BOLD}📊 Resultados de la Auditoría{Colors.END}\n")
    
    critical_found = False
    warnings_found = False
    
    # Problemas Críticos
    critical_categories = ['facades', 'models_direct', 'schemas_direct', 'routes_direct', 'repositories']
    
    for category in critical_categories:
        count = total_issues[category]
        if count > 0:
            critical_found = True
            print(f"{Colors.RED}🔴 CRÍTICO - {category}:{Colors.END}")
            print(f"   {count} ocurrencias en {len(files_with_issues[category])} archivos")
            print(f"   Archivos afectados (primeros 3 con detalles):")
            
            for idx, file in enumerate(sorted(files_with_issues[category])[:3], 1):
                print(f"\n     {idx}. {Colors.BOLD}{file}{Colors.END}")
                occurrences = detailed_issues[category][file][:3]  # Primeras 3 líneas
                for line_num, line_content in occurrences:
                    print(f"        Línea {line_num}: {line_content}")
                if len(detailed_issues[category][file]) > 3:
                    print(f"        ... y {len(detailed_issues[category][file]) - 3} más en este archivo")
            
            if len(files_with_issues[category]) > 3:
                print(f"\n     ... y {len(files_with_issues[category]) - 3} archivos más con este problema")
            print()
    
    # Advertencias
    warning_categories = ['services_direct', 'enums_direct']
    
    for category in warning_categories:
        count = total_issues[category]
        if count > 0:
            warnings_found = True
            print(f"{Colors.YELLOW}🟡 ADVERTENCIA - {category}:{Colors.END}")
            print(f"   {count} ocurrencias en {len(files_with_issues[category])} archivos")
            print(f"   Nota: Verificar si estos servicios deberían estar en módulos")
            print(f"   Archivos afectados:")
            for file in sorted(files_with_issues[category])[:5]:
                print(f"     • {file}")
            if len(files_with_issues[category]) > 5:
                print(f"     ... y {len(files_with_issues[category]) - 5} más")
            print()
    
    # Verificar existencia de archivos críticos
    print(f"{Colors.BOLD}🔍 Verificación de Archivos Críticos{Colors.END}\n")
    
    critical_files = [
        ("app/routes.py", "Router principal (importado en main.py)"),
        ("app/shared/config/settings.py", "Settings consolidado"),
        ("app/shared/database/database.py", "Configuración de DB"),
        ("app/shared/utils/security.py", "Utilidades de seguridad"),
    ]
    
    missing_files = []
    for file_path, description in critical_files:
        full_path = backend_root / file_path
        if not full_path.exists():
            print(f"{Colors.RED}❌ FALTA: {file_path}{Colors.END}")
            print(f"   Descripción: {description}")
            missing_files.append(file_path)
        else:
            print(f"{Colors.GREEN}✅ OK: {file_path}{Colors.END}")
    
    print()
    
    # Resumen final
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}RESUMEN EJECUTIVO{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    total_critical = sum(total_issues[cat] for cat in critical_categories)
    total_warnings = sum(total_issues[cat] for cat in warning_categories)
    
    if not critical_found and not warnings_found and not missing_files:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ EXCELENTE - No se encontraron problemas{Colors.END}")
        print(f"{Colors.GREEN}El backend está listo para ejecutarse{Colors.END}")
        return 0
    else:
        if critical_found or missing_files:
            print(f"{Colors.RED}{Colors.BOLD}🔴 PROBLEMAS CRÍTICOS ENCONTRADOS{Colors.END}")
            print(f"{Colors.RED}   • {total_critical} imports críticos rotos{Colors.END}")
            print(f"{Colors.RED}   • {len(missing_files)} archivos críticos faltantes{Colors.END}")
            print(f"{Colors.RED}   El backend NO puede iniciar correctamente{Colors.END}\n")
        
        if warnings_found:
            print(f"{Colors.YELLOW}{Colors.BOLD}🟡 ADVERTENCIAS{Colors.END}")
            print(f"{Colors.YELLOW}   • {total_warnings} imports que requieren revisión{Colors.END}")
            print(f"{Colors.YELLOW}   Verificar si estos servicios están en la ubicación correcta{Colors.END}\n")
        
        print(f"{Colors.BOLD}📋 ACCIÓN REQUERIDA:{Colors.END}")
        print(f"   1. Revisar el archivo AUDITORIA_BACKEND.md para más detalles")
        print(f"   2. Resolver los problemas críticos antes de iniciar el backend")
        print(f"   3. Considerar crear wrappers de compatibilidad temporales")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())
