#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/validate_openapi.py

Script de validación de OpenAPI para verificar que todas las rutas
cumplen con los estándares establecidos:

1. Todas las rutas comienzan con /api/
2. No hay duplicados (path+method)
3. Todos los tags pertenecen al catálogo oficial

Autor: DoxAI
Fecha: 2025-10-18
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Set
import httpx

# Tags oficiales del catálogo
OFFICIAL_TAGS = {
    "Authentication",
    "User Profile",
    "Files",
    "Projects",
    "RAG",
    "Payments",
}


def fetch_openapi_spec(base_url: str = "http://localhost:8000") -> Dict:
    """Obtiene el spec OpenAPI del servidor."""
    try:
        response = httpx.get(f"{base_url}/openapi.json", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error al obtener OpenAPI spec: {e}")
        sys.exit(1)


def validate_api_prefix(paths: Dict) -> List[str]:
    """Valida que todas las rutas comiencen con /api/."""
    errors = []
    
    for path in paths.keys():
        if not path.startswith("/api/"):
            # Excepciones: endpoints de health y root
            if path in ["/", "/health", "/api/health/live", "/api/health/ready"]:
                continue
            errors.append(f"Ruta sin prefijo /api/: {path}")
    
    return errors


def validate_no_duplicates(paths: Dict) -> List[str]:
    """Valida que no haya duplicados de path+method."""
    errors = []
    seen = set()
    
    for path, methods in paths.items():
        for method in methods.keys():
            if method == "parameters":  # Skip metadata
                continue
            
            key = f"{method.upper()}:{path}"
            if key in seen:
                errors.append(f"Ruta duplicada: {method.upper()} {path}")
            seen.add(key)
    
    return errors


def validate_official_tags(paths: Dict) -> List[str]:
    """Valida que todos los tags sean oficiales."""
    errors = []
    unofficial_tags = set()
    
    for path, methods in paths.items():
        for method, details in methods.items():
            if method == "parameters":  # Skip metadata
                continue
            
            tags = details.get("tags", [])
            for tag in tags:
                if tag not in OFFICIAL_TAGS:
                    unofficial_tags.add(tag)
                    errors.append(f"Tag no oficial en {method.upper()} {path}: '{tag}'")
    
    return errors, unofficial_tags


def validate_tag_descriptions(spec: Dict) -> List[str]:
    """Valida que todos los tags oficiales tengan descripción."""
    errors = []
    
    defined_tags = {tag["name"] for tag in spec.get("tags", [])}
    
    for official_tag in OFFICIAL_TAGS:
        if official_tag not in defined_tags:
            errors.append(f"Tag oficial sin definición en OpenAPI: '{official_tag}'")
    
    return errors


def generate_report(spec: Dict) -> int:
    """Genera reporte completo de validación."""
    print("=" * 80)
    print("🔍 VALIDACIÓN DE OPENAPI - DoxAI")
    print("=" * 80)
    print()
    
    paths = spec.get("paths", {})
    total_paths = len(paths)
    total_endpoints = sum(
        len([m for m in methods.keys() if m != "parameters"])
        for methods in paths.values()
    )
    
    print(f"📊 Estadísticas:")
    print(f"  • Total de paths: {total_paths}")
    print(f"  • Total de endpoints: {total_endpoints}")
    print()
    
    # Validaciones
    all_errors = []
    
    # 1. Prefijo /api/
    print("1️⃣  Validando prefijo /api/...")
    prefix_errors = validate_api_prefix(paths)
    if prefix_errors:
        all_errors.extend(prefix_errors)
        print(f"   ❌ {len(prefix_errors)} rutas sin prefijo /api/")
        for error in prefix_errors[:5]:  # Mostrar solo primeras 5
            print(f"      - {error}")
        if len(prefix_errors) > 5:
            print(f"      ... y {len(prefix_errors) - 5} más")
    else:
        print("   ✅ Todas las rutas tienen prefijo /api/")
    print()
    
    # 2. Duplicados
    print("2️⃣  Validando duplicados...")
    duplicate_errors = validate_no_duplicates(paths)
    if duplicate_errors:
        all_errors.extend(duplicate_errors)
        print(f"   ❌ {len(duplicate_errors)} duplicados encontrados")
        for error in duplicate_errors:
            print(f"      - {error}")
    else:
        print("   ✅ No hay duplicados de path+method")
    print()
    
    # 3. Tags oficiales
    print("3️⃣  Validando tags...")
    tag_errors, unofficial_tags = validate_official_tags(paths)
    if tag_errors:
        all_errors.extend(tag_errors)
        print(f"   ❌ {len(unofficial_tags)} tags no oficiales encontrados:")
        for tag in sorted(unofficial_tags):
            print(f"      - '{tag}'")
    else:
        print("   ✅ Todos los tags son oficiales")
    print()
    
    # 4. Definiciones de tags
    print("4️⃣  Validando definiciones de tags...")
    tag_def_errors = validate_tag_descriptions(spec)
    if tag_def_errors:
        all_errors.extend(tag_def_errors)
        print(f"   ⚠️  {len(tag_def_errors)} tags sin definición")
        for error in tag_def_errors:
            print(f"      - {error}")
    else:
        print("   ✅ Todos los tags están definidos")
    print()
    
    # Resumen
    print("=" * 80)
    if all_errors:
        print(f"❌ VALIDACIÓN FALLIDA: {len(all_errors)} errores encontrados")
        print("=" * 80)
        return 1
    else:
        print("✅ VALIDACIÓN EXITOSA: Todos los checks pasaron")
        print("=" * 80)
        return 0


def save_validation_report(spec: Dict, output_path: Path):
    """Guarda reporte de validación en markdown."""
    paths = spec.get("paths", {})
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# 📋 Reporte de Validación OpenAPI - DoxAI\n\n")
        f.write(f"**Fecha**: {Path(__file__).stat().st_mtime}\n")
        f.write(f"**Versión API**: {spec.get('info', {}).get('version', 'N/A')}\n\n")
        
        f.write("## ✅ Validaciones Ejecutadas\n\n")
        
        # Prefijo /api/
        prefix_errors = validate_api_prefix(paths)
        f.write("### 1. Prefijo /api/\n\n")
        if prefix_errors:
            f.write(f"❌ **{len(prefix_errors)} rutas sin prefijo**\n\n")
            for error in prefix_errors:
                f.write(f"- {error}\n")
        else:
            f.write("✅ **Todas las rutas tienen prefijo /api/**\n")
        f.write("\n")
        
        # Duplicados
        duplicate_errors = validate_no_duplicates(paths)
        f.write("### 2. Duplicados\n\n")
        if duplicate_errors:
            f.write(f"❌ **{len(duplicate_errors)} duplicados encontrados**\n\n")
            for error in duplicate_errors:
                f.write(f"- {error}\n")
        else:
            f.write("✅ **No hay duplicados de path+method**\n")
        f.write("\n")
        
        # Tags
        tag_errors, unofficial_tags = validate_official_tags(paths)
        f.write("### 3. Tags Oficiales\n\n")
        if unofficial_tags:
            f.write(f"❌ **{len(unofficial_tags)} tags no oficiales**\n\n")
            f.write("| Tag No Oficial | Sugerencia |\n")
            f.write("|----------------|------------|\n")
            for tag in sorted(unofficial_tags):
                f.write(f"| `{tag}` | Consolidar en tag oficial |\n")
        else:
            f.write("✅ **Todos los tags son oficiales**\n")
        f.write("\n")
        
        # Resumen
        f.write("## 📊 Resumen\n\n")
        total_errors = len(prefix_errors) + len(duplicate_errors) + len(tag_errors)
        
        if total_errors == 0:
            f.write("✅ **Todas las validaciones pasaron exitosamente**\n")
        else:
            f.write(f"❌ **Total de errores: {total_errors}**\n\n")
            f.write("### Errores por categoría:\n\n")
            f.write(f"- Prefijo /api/: {len(prefix_errors)}\n")
            f.write(f"- Duplicados: {len(duplicate_errors)}\n")
            f.write(f"- Tags no oficiales: {len(tag_errors)}\n")


def main():
    """Función principal."""
    print("\n🚀 Iniciando validación de OpenAPI...\n")
    
    # Obtener spec
    spec = fetch_openapi_spec()
    
    # Generar reporte en consola
    exit_code = generate_report(spec)
    
    # Guardar reporte en archivo
    output_path = Path(__file__).parent.parent / "docs" / "openapi_validation.md"
    output_path.parent.mkdir(exist_ok=True)
    save_validation_report(spec, output_path)
    
    print(f"\n📝 Reporte guardado en: {output_path.relative_to(Path.cwd())}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
