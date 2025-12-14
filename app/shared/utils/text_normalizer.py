# -*- coding: utf-8 -*-
"""
backend/app/utils/text_normalizer.py

Utilidades para normalización de texto para mejorar ratio de cache hits
en embeddings deduplicados.

Autor: Sistema DoxAI
Fecha: 05/09/2025
"""

import re
from typing import Optional


def normalize_for_hash(text: str) -> str:
    """
    Normaliza texto para generar hash consistente y mejorar cache hits.
    
    - Convierte a minúsculas
    - Colapsa espacios en blanco múltiples
    - Elimina números de página simples
    - Elimina headers/footers triviales
    - Mantiene estructura semántica importante
    
    Args:
        text: Texto original del chunk
        
    Returns:
        Texto normalizado para hashing
    """
    if not text or not text.strip():
        return ""
    
    # Convertir a minúsculas y strip inicial
    normalized = text.lower().strip()
    
    # Eliminar números de página simples (ej: "página 1", "page 2", "1/10")
    page_patterns = [
        r'\bpágina?\s+\d+\b',
        r'\bpage?\s+\d+\b', 
        r'\b\d+\s*/\s*\d+\b',
        r'^\s*\d+\s*$'  # Solo números
    ]
    
    for pattern in page_patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    
    # Eliminar headers/footers comunes triviales
    trivial_patterns = [
        r'\bconfidencial\b',
        r'\breservados?\s+todos?\s+los\s+derechos?\b',
        r'\bcopyright\s*©?\s*\d*\b',
        r'\b©\s*\d*\b'
    ]
    
    for pattern in trivial_patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    
    # Colapsar espacios múltiples pero mantener saltos de línea significativos
    normalized = re.sub(r'[ \t]+', ' ', normalized)  # Solo espacios/tabs horizontales
    normalized = re.sub(r'\n\s*\n\s*\n+', '\n\n', normalized)  # Máximo 2 newlines seguidos
    
    # Eliminar espacios al inicio/final de cada línea
    lines = [line.strip() for line in normalized.split('\n')]
    normalized = '\n'.join(line for line in lines if line)  # Eliminar líneas vacías
    
    return normalized.strip()


def extract_content_fingerprint(text: str, max_length: int = 256) -> str:
    """
    Extrae una huella dactilar del contenido para usar en hashes rápidos.
    
    Toma los primeros y últimos caracteres del texto normalizado
    para crear un fingerprint que capture la esencia del contenido
    sin procesar texto completo.
    
    Args:
        text: Texto normalizado
        max_length: Máximo caracteres para el fingerprint
        
    Returns:
        Fingerprint del contenido
    """
    if not text or len(text) <= max_length:
        return text
    
    # Tomar inicio y final del texto
    half = max_length // 2
    start = text[:half]
    end = text[-half:]
    
    return f"{start}...{end}"


def should_skip_embedding(text: str, min_meaningful_chars: int = 10) -> bool:
    """
    Determina si un texto es demasiado trivial para embeddear.
    
    Args:
        text: Texto del chunk
        min_meaningful_chars: Mínimo caracteres significativos
        
    Returns:
        True si se debe saltar el embedding
    """
    if not text or not text.strip():
        return True
        
    # Contar solo caracteres alfanuméricos
    meaningful_chars = len(re.sub(r'[^\w]', '', text))
    
    if meaningful_chars < min_meaningful_chars:
        return True
        
    # Detectar texto repetitivo trivial
    words = text.lower().split()
    if len(set(words)) < len(words) * 0.3:  # Menos del 30% de palabras únicas
        return True
        
    return False






