# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_table_deduplication_service.py

Table deduplication and normalization utilities.
Handles merging tables from multiple extraction sources.

Author: Ixchel Beristain Mendoza
Refactored: 28/09/2025
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging
import hashlib

logger = logging.getLogger(__name__)


def normalize_and_dedupe_tables(
    pdfplumber_tables: List[Dict[str, Any]],
    unstructured_tables: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Normaliza y deduplica tablas de múltiples fuentes comparando headers y contenido.
    
    Args:
        pdfplumber_tables: Tablas extraídas con pdfplumber
        unstructured_tables: Tablas de unstructured (opcional)
        
    Returns:
        Lista deduplicada de tablas normalizadas
    """
    all_tables = []
    all_tables.extend(pdfplumber_tables)
    if unstructured_tables:
        all_tables.extend(unstructured_tables)
    
    if not all_tables:
        return []
    
    # Agrupar por página para comparación local
    tables_by_page = _group_tables_by_page(all_tables)
    final_tables = []
    
    for page, page_tables in tables_by_page.items():
        if len(page_tables) == 1:
            # Solo una tabla en la página, incluir directamente
            final_tables.append(page_tables[0])
            continue
        
        # Múltiples tablas, buscar duplicados
        unique_tables = _dedupe_similar_tables(page_tables)
        final_tables.extend(unique_tables)
    
    # Añadir deduplicación por hash de contenido para evitar duplicados exactos
    final_tables = dedupe_tables_by_content_hash(final_tables)
    
    logger.info(f"🔄 Normalización completada: {len(all_tables)} → {len(final_tables)} tablas")
    return final_tables


def dedupe_tables_by_content_hash(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate tables based on content hash to avoid processing identical tables.
    
    Args:
        tables: Lista de tablas a deduplicar
        
    Returns:
        Lista de tablas sin duplicados exactos
    """
    seen_hashes = set()
    unique_tables = []
    
    for table in tables:
        rows = table.get("rows", [])
        if not rows:
            continue
            
        # Create content hash from rows
        content_str = str(sorted([str(row) for row in rows]))
        content_hash = hashlib.md5(content_str.encode()).hexdigest()
        
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique_tables.append(table)
        else:
            logger.debug(f"🔄 Deduplicating table: {table.get('table_id', 'unknown')} (hash: {content_hash[:8]})")
    
    if len(tables) != len(unique_tables):
        logger.info(f"🔄 Table deduplication: {len(tables)} → {len(unique_tables)} tables")
    
    return unique_tables


def _group_tables_by_page(tables: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Agrupa tablas por número de página.
    
    Args:
        tables: Lista de tablas
        
    Returns:
        Diccionario con tablas agrupadas por página
    """
    tables_by_page: Dict[int, List[Dict[str, Any]]] = {}
    
    for table in tables:
        page = table.get("page")
        if page:
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)
    
    return tables_by_page


def _dedupe_similar_tables(page_tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplica tablas similares en una página, manteniendo la de mayor confianza.
    
    Args:
        page_tables: Lista de tablas en una página
        
    Returns:
        Lista de tablas únicas
    """
    unique_tables = []
    
    for table in page_tables:
        is_duplicate = False
        
        for existing in unique_tables:
            if tables_are_similar(table, existing):
                # Es duplicado, mantener la de mayor confianza
                if table.get("confidence", 0) > existing.get("confidence", 0):
                    unique_tables.remove(existing)
                    unique_tables.append(table)
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_tables.append(table)
    
    return unique_tables


def tables_are_similar(table1: Dict[str, Any], table2: Dict[str, Any]) -> bool:
    """
    Compara dos tablas para determinar si son similares (posibles duplicados).
    Compara headers, dimensiones y una muestra del contenido.
    
    Args:
        table1: Primera tabla a comparar
        table2: Segunda tabla a comparar
        
    Returns:
        True si las tablas son similares
    """
    rows1 = table1.get("rows", [])
    rows2 = table2.get("rows", [])
    
    if not rows1 or not rows2:
        return False
    
    # Comparar dimensiones
    if len(rows1) != len(rows2) or len(rows1[0]) != len(rows2[0]):
        return False
    
    # Comparar headers (primera fila)
    header1 = [str(cell).strip().lower() for cell in rows1[0]]
    header2 = [str(cell).strip().lower() for cell in rows2[0]]
    
    if header1 != header2:
        return False
    
    # Comparar una muestra del contenido (primera fila de datos)
    if len(rows1) > 1 and len(rows2) > 1:
        data1 = [str(cell).strip().lower() for cell in rows1[1]]
        data2 = [str(cell).strip().lower() for cell in rows2[1]]
        
        # Calcular similitud (permitir algunas diferencias menores)
        matches = sum(1 for c1, c2 in zip(data1, data2) if c1 == c2)
        similarity = matches / len(data1) if data1 else 0
        
        return similarity >= 0.8  # 80% de similitud
    
    return True  # Solo headers, considerar similares






