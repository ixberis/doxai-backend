#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/report_routes.py

Script de análisis de rutas de FastAPI para detectar:
- Paths con doble prefijo
- Paths sin /api/
- Tags fuera del catálogo oficial
- Duplicados de paths+methods

Autor: DoxAI
Fecha: 2025-10-18
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Set
import csv

# Tags oficiales del catálogo
OFFICIAL_TAGS = {
    "Authentication",
    "User Profile", 
    "Files",
    "Projects",
    "RAG",
    "Payments"
}

# Regex para detectar doble prefijo
DOUBLE_PREFIX_PATTERN = re.compile(
    r'^/(api/)?(auth|files|projects|rag|payments)/(auth|files|projects|rag|payments)/'
)


def analyze_router_file(file_path: Path) -> Dict:
    """Analiza un archivo de rutas y extrae información"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extraer definición del router
    router_match = re.search(
        r'router\s*=\s*APIRouter\((.*?)\)',
        content,
        re.DOTALL
    )
    
    router_info = {
        'file': str(file_path.relative_to(Path.cwd() / 'backend')),
        'prefix': '',
        'tags': [],
        'routes': []
    }
    
    if router_match:
        router_def = router_match.group(1)
        
        # Extraer prefix
        prefix_match = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', router_def)
        if prefix_match:
            router_info['prefix'] = prefix_match.group(1)
        
        # Extraer tags
        tags_match = re.search(r'tags\s*=\s*\[(.*?)\]', router_def)
        if tags_match:
            tags_str = tags_match.group(1)
            tags = re.findall(r'["\']([^"\']+)["\']', tags_str)
            router_info['tags'] = tags
    
    # Extraer rutas
    route_pattern = re.compile(
        r'@router\.(get|post|put|patch|delete)\(["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    
    for match in route_pattern.finditer(content):
        method = match.group(1).upper()
        path = match.group(2)
        router_info['routes'].append({
            'method': method,
            'path': path
        })
    
    return router_info


def construct_full_path(router_prefix: str, route_path: str, include_prefix: str = '') -> str:
    """Construye el path completo combinando prefijos"""
    parts = []
    
    # Agregar prefix de inclusión en routes.py
    if include_prefix:
        parts.append(include_prefix.strip('/'))
    
    # Agregar prefix del router
    if router_prefix:
        parts.append(router_prefix.strip('/'))
    
    # Agregar path de la ruta
    if route_path and route_path != '/':
        parts.append(route_path.strip('/'))
    
    full_path = '/' + '/'.join(parts) if parts else '/'
    return full_path


def detect_issues(full_path: str, tags: List[str]) -> List[str]:
    """Detecta problemas en una ruta"""
    issues = []
    
    # Detectar doble prefijo
    if DOUBLE_PREFIX_PATTERN.match(full_path):
        issues.append("DOUBLE_PREFIX")
    
    # Detectar falta de /api/
    if not full_path.startswith('/api/'):
        issues.append("NO_API_PREFIX")
    
    # Detectar tags no oficiales
    for tag in tags:
        if tag not in OFFICIAL_TAGS:
            issues.append(f"UNOFFICIAL_TAG:{tag}")
    
    return issues


def main():
    """Función principal del script"""
    print("🔍 Analizando estructura de rutas de DoxAI...\n")
    
    # Mapeo de inclusiones en routes.py (basado en el código actual)
    # formato: 'archivo': 'prefix_de_inclusion'
    ROUTER_INCLUSIONS = {
        'app/modules/auth/routes/auth_routes.py': '/auth',
        'app/modules/user_profile/routes/profile_routes.py': '',
        'app/modules/files/routes/file_routes.py': '/files',
        'app/modules/files/routes/selected_download_routes.py': '/files',
        'app/modules/projects/routes/project_routes.py': '',
        'app/modules/projects/routes/bulk_download_input_files_routes.py': '/projects',
        'app/modules/projects/routes/bulk_download_product_files_routes.py': '/projects',
        'app/modules/projects/routes/selected_download_input_files_routes.py': '/projects',
        'app/modules/projects/routes/selected_download_product_files_routes.py': '/projects',
        'app/modules/rag/routes/rag_routes.py': '/rag',
        'app/modules/payments/routes/abandoned_payment_router.py': '/payments',
        'app/modules/payments/routes/payment_confirmation_router.py': '/payments',
        'app/modules/payments/routes/payment_webhooks_router.py': '/payments/webhooks',
        'app/modules/payments/routes/resume_payment_router.py': '/payments',
        'app/modules/payments/routes/subscription_session_router.py': '/payments',
        'app/modules/payments/routes/subscription_status_router.py': '/payments',
    }
    
    base_path = Path.cwd() / 'backend'
    all_routes = []
    all_issues = []
    paths_seen = {}  # Para detectar duplicados
    
    # Analizar cada archivo de rutas
    for router_file, include_prefix in ROUTER_INCLUSIONS.items():
        file_path = base_path / router_file
        
        if not file_path.exists():
            print(f"⚠️  Archivo no encontrado: {router_file}")
            continue
        
        print(f"📄 Analizando: {router_file}")
        router_info = analyze_router_file(file_path)
        
        # Construir paths completos
        for route in router_info['routes']:
            full_path = construct_full_path(
                router_info['prefix'],
                route['path'],
                include_prefix
            )
            
            # Detectar problemas
            issues = detect_issues(full_path, router_info['tags'])
            
            # Detectar duplicados
            key = f"{route['method']}:{full_path}"
            if key in paths_seen:
                issues.append(f"DUPLICATE:with_{paths_seen[key]}")
                all_issues.append({
                    'issue': 'DUPLICATE',
                    'path': full_path,
                    'method': route['method'],
                    'file1': paths_seen[key],
                    'file2': router_file
                })
            else:
                paths_seen[key] = router_file
            
            route_entry = {
                'file': router_file,
                'method': route['method'],
                'router_prefix': router_info['prefix'],
                'include_prefix': include_prefix,
                'route_path': route['path'],
                'full_path': full_path,
                'tags': '|'.join(router_info['tags']),
                'issues': '|'.join(issues) if issues else 'OK'
            }
            
            all_routes.append(route_entry)
            
            if issues:
                all_issues.append({
                    'issue': issues[0],
                    'path': full_path,
                    'method': route['method'],
                    'file': router_file
                })
    
    # Escribir CSV
    csv_path = base_path / 'docs' / 'routes_current.csv'
    csv_path.parent.mkdir(exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'file', 'method', 'router_prefix', 'include_prefix', 
            'route_path', 'full_path', 'tags', 'issues'
        ])
        writer.writeheader()
        writer.writerows(all_routes)
    
    print(f"\n✅ CSV generado: {csv_path.relative_to(Path.cwd())}")
    
    # Resumen de problemas
    print("\n" + "="*80)
    print("📊 RESUMEN DE PROBLEMAS DETECTADOS")
    print("="*80)
    
    issue_counts = {}
    for route in all_routes:
        if route['issues'] != 'OK':
            for issue in route['issues'].split('|'):
                issue_type = issue.split(':')[0]
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
    
    if issue_counts:
        for issue_type, count in sorted(issue_counts.items()):
            print(f"  • {issue_type}: {count} rutas")
        
        print(f"\n📝 Total de rutas con problemas: {len([r for r in all_routes if r['issues'] != 'OK'])}")
        print(f"📝 Total de rutas OK: {len([r for r in all_routes if r['issues'] == 'OK'])}")
    else:
        print("  ✨ ¡No se detectaron problemas!")
    
    print(f"\n📝 Total de rutas analizadas: {len(all_routes)}")
    print("="*80)
    
    # Generar informe de hallazgos
    generate_findings_report(all_routes, all_issues, base_path)
    
    return 0 if not issue_counts else 1


def generate_findings_report(all_routes: List[Dict], all_issues: List[Dict], base_path: Path):
    """Genera el documento de hallazgos"""
    findings_path = base_path / 'docs' / 'routes_findings.md'
    
    with open(findings_path, 'w', encoding='utf-8') as f:
        f.write("# 🔍 Hallazgos del Análisis de Rutas - DoxAI\n\n")
        f.write(f"**Fecha**: 2025-10-18\n")
        f.write(f"**Total de rutas**: {len(all_routes)}\n\n")
        
        f.write("## 📋 Resumen Ejecutivo\n\n")
        
        # Contar problemas
        double_prefix = len([r for r in all_routes if 'DOUBLE_PREFIX' in r['issues']])
        no_api = len([r for r in all_routes if 'NO_API_PREFIX' in r['issues']])
        unofficial_tags = len([r for r in all_routes if 'UNOFFICIAL_TAG' in r['issues']])
        
        f.write(f"- **Rutas con doble prefijo**: {double_prefix}\n")
        f.write(f"- **Rutas sin /api/ prefix**: {no_api}\n")
        f.write(f"- **Rutas con tags no oficiales**: {unofficial_tags}\n\n")
        
        f.write("## 🔴 Problemas Críticos\n\n")
        
        # Doble prefijo
        if double_prefix:
            f.write("### Doble Prefijo\n\n")
            f.write("Rutas donde el prefijo se duplica:\n\n")
            f.write("| Archivo | Método | Path Actual | Path Esperado |\n")
            f.write("|---------|--------|-------------|---------------|\n")
            
            for route in all_routes:
                if 'DOUBLE_PREFIX' in route['issues']:
                    expected = route['full_path'].replace(
                        f"/{route['router_prefix'].strip('/')}/{route['router_prefix'].strip('/')}/",
                        f"/{route['router_prefix'].strip('/')}/"
                    )
                    f.write(f"| {route['file'].split('/')[-1]} | {route['method']} | `{route['full_path']}` | `{expected}` |\n")
            
            f.write("\n")
        
        # Sin /api/
        if no_api:
            f.write("### Sin Prefijo /api/\n\n")
            f.write("Rutas que no comienzan con `/api/`:\n\n")
            f.write("| Archivo | Método | Path Actual | Path Esperado |\n")
            f.write("|---------|--------|-------------|---------------|\n")
            
            for route in all_routes:
                if 'NO_API_PREFIX' in route['issues']:
                    expected = f"/api{route['full_path']}"
                    f.write(f"| {route['file'].split('/')[-1]} | {route['method']} | `{route['full_path']}` | `{expected}` |\n")
            
            f.write("\n")
        
        # Tags no oficiales
        if unofficial_tags:
            f.write("### Tags No Oficiales\n\n")
            f.write("Tags encontrados que no están en el catálogo:\n\n")
            
            unofficial_tags_set = set()
            for route in all_routes:
                for issue in route['issues'].split('|'):
                    if issue.startswith('UNOFFICIAL_TAG:'):
                        unofficial_tags_set.add(issue.split(':')[1])
            
            f.write("| Tag Actual | Tag Oficial Sugerido |\n")
            f.write("|------------|----------------------|\n")
            
            tag_mapping = {
                'user-profile': 'User Profile',
                'projects': 'Projects',
                'payments': 'Payments',
                'abandonment': 'Payments',
                'resume_payment': 'Payments',
                'subscriptions': 'Payments',
                'webhooks': 'Payments',
                'Bulk Download': 'Projects',
                'Downloads': 'Projects',
                'Input Files': 'Files',
                'Product Files': 'Files'
            }
            
            for tag in sorted(unofficial_tags_set):
                suggested = tag_mapping.get(tag, '❓')
                f.write(f"| `{tag}` | `{suggested}` |\n")
            
            f.write("\n")
        
        f.write("## 📝 Recomendaciones\n\n")
        f.write("1. **Estandarizar prefijos**: Agregar `/api` global en routes.py\n")
        f.write("2. **Eliminar duplicaciones**: Remover prefijos en decoradores cuando ya existen en router\n")
        f.write("3. **Unificar tags**: Usar solo los tags oficiales del catálogo\n")
        f.write("4. **Consolidar módulos**: Agrupar rutas relacionadas bajo un mismo router\n\n")
        
        f.write("## ✅ Siguientes Pasos\n\n")
        f.write("- [ ] Revisar routes.py y agregar prefix=\"/api\" global\n")
        f.write("- [ ] Actualizar cada router para usar prefixes sin /api\n")
        f.write("- [ ] Modificar decoradores para usar paths relativos\n")
        f.write("- [ ] Actualizar tags a los oficiales\n")
        f.write("- [ ] Crear mapa de migración de endpoints\n")
        f.write("- [ ] Implementar redirects temporales para compatibilidad\n")
    
    print(f"✅ Informe generado: {findings_path.relative_to(Path.cwd())}\n")


if __name__ == '__main__':
    sys.exit(main())
