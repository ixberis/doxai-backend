# -*- coding: utf-8 -*-
"""
backend/app/utils/storage_pagination_utils.py

**UTILIDADES DE PAGINACIÓN PARA SUPABASE STORAGE**

Funciones auxiliares para manejar paginación en operaciones de storage:
- Listar archivos con paginación
- Calcular offsets y límites
- Gestión de cursores de paginación

Autor: DoxAI
Fecha: 29 de septiembre de 2025 (FASE 2)
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class StoragePagination:
    """Helper para paginación de archivos en storage."""
    
    def __init__(self, page_size: int = 100):
        self.page_size = page_size
        self.current_page = 0
        self.total_items = 0
        self.has_more = True
    
    @property
    def offset(self) -> int:
        """Calcula offset actual."""
        return self.current_page * self.page_size
    
    def next_page(self):
        """Avanza a la siguiente página."""
        if self.has_more:
            self.current_page += 1
    
    def reset(self):
        """Reinicia paginación."""
        self.current_page = 0
        self.total_items = 0
        self.has_more = True
    
    def update_from_response(self, items: List[Any], expected_size: Optional[int] = None):
        """
        Actualiza estado de paginación desde respuesta.
        
        Args:
            items: Lista de items recibidos
            expected_size: Tamaño esperado (si difiere, no hay más páginas)
        """
        items_count = len(items)
        self.total_items += items_count
        
        # Si recibimos menos items que el page_size, no hay más páginas
        if expected_size is None:
            expected_size = self.page_size
        
        self.has_more = items_count >= expected_size
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de paginación."""
        return {
            'current_page': self.current_page,
            'page_size': self.page_size,
            'offset': self.offset,
            'total_items': self.total_items,
            'has_more': self.has_more
        }


def calculate_pagination(
    total: Optional[int],
    page_size: int,
    current_offset: int
) -> Dict[str, Any]:
    """
    Calcula información de paginación.
    
    Args:
        total: Total de items (None si desconocido)
        page_size: Tamaño de página
        current_offset: Offset actual
        
    Returns:
        Dict con info de paginación
    """
    current_page = current_offset // page_size
    
    result = {
        'page_size': page_size,
        'current_page': current_page,
        'current_offset': current_offset,
        'next_offset': current_offset + page_size
    }
    
    if total is not None:
        total_pages = (total + page_size - 1) // page_size
        has_more = current_offset + page_size < total
        
        result.update({
            'total': total,
            'total_pages': total_pages,
            'has_more': has_more,
            'remaining': max(0, total - (current_offset + page_size))
        })
    
    return result


def extract_files_from_storage_response(
    response: Any
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Extrae lista de archivos de respuesta de storage.
    
    Maneja diferentes formatos de respuesta de Supabase Storage.
    
    Args:
        response: Respuesta del cliente de storage
        
    Returns:
        (lista_de_archivos, hay_mas)
    """
    if not response:
        return [], False
    
    # Caso 1: Dict con 'files' y 'has_more'
    if isinstance(response, dict):
        files = response.get('files', response.get('data', []))
        has_more = response.get('has_more', False)
        return files, has_more
    
    # Caso 2: Lista directa
    if isinstance(response, list):
        return response, False  # No sabemos si hay más
    
    # Caso 3: Otro formato
    logger.warning(f"Formato de respuesta inesperado: {type(response)}")
    return [], False


def format_file_info(file_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formatea información de archivo de storage.
    
    Args:
        file_data: Datos crudos del archivo
        
    Returns:
        Dict formateado con campos estándar
    """
    return {
        'name': file_data.get('name', ''),
        'path': file_data.get('id', file_data.get('name', '')),
        'size': file_data.get('metadata', {}).get('size', 0),
        'created_at': file_data.get('created_at', ''),
        'updated_at': file_data.get('updated_at', ''),
        'content_type': file_data.get('metadata', {}).get('mimetype', ''),
        'bucket': file_data.get('bucket_id', '')
    }


def batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    """
    Divide lista en batches de tamaño fijo.
    
    Args:
        items: Lista de items
        batch_size: Tamaño de cada batch
        
    Returns:
        Lista de batches
    """
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]







