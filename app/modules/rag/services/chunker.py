# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/chunker.py

Servicio de chunking semántico para documentos.
Divide texto en chunks optimizados para embeddings y búsqueda.

Autor: DoxAI
Fecha: 2025-10-28
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class ChunkParams:
    """Parámetros de chunking."""
    max_tokens: int = 512
    overlap: int = 50


@dataclass
class ChunkDTO:
    """DTO para un chunk individual."""
    index: int
    text: str
    token_count: int
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    chunk_type: str = "paragraph"
    chunk_metadata: Optional[Dict[str, Any]] = None


class ChunkerService:
    """
    Servicio de chunking semántico.
    
    Estrategias:
        - Respeta límites de párrafos
        - Aplica overlap entre chunks
        - Mantiene contexto semántico
        - Preserva metadata de origen (páginas)
    """
    
    def __init__(self, tokenizer=None):
        """
        Inicializa el chunker.
        
        Args:
            tokenizer: Tokenizer compatible con el modelo de embeddings
                      (ej: tiktoken para OpenAI)
        """
        self.tokenizer = tokenizer
    
    async def make_chunks(
        self,
        text_uri: str,
        params: ChunkParams
    ) -> List[ChunkDTO]:
        """
        Divide texto en chunks semánticos.
        
        Args:
            text_uri: URI del texto fuente en storage
            params: Parámetros de chunking (max_tokens, overlap)
            
        Returns:
            Lista de ChunkDTO con chunks y metadata
            
        Raises:
            NotImplementedError: Pendiente implementación
            
        Notes:
            - Respeta límites de párrafos cuando sea posible
            - Aplica overlap para mantener contexto
            - Calcula token_count con tokenizer apropiado
            - Preserva información de páginas fuente
        """
        # TODO: Implementación completa
        # 1. Cargar texto de text_uri
        # 2. Detectar párrafos y secciones
        # 3. Dividir en chunks respetando max_tokens:
        #    - Intentar no partir párrafos
        #    - Si un párrafo excede max_tokens, dividirlo por oraciones
        #    - Aplicar overlap entre chunks
        # 4. Calcular token_count para cada chunk
        # 5. Preservar source_page_start/end si disponible
        # 6. Determinar chunk_type (paragraph, heading, table, etc.)
        # 7. Retornar List[ChunkDTO]
        
        raise NotImplementedError(
            f"Chunking pending for text_uri={text_uri}, max_tokens={params.max_tokens}"
        )
    
    def _count_tokens(self, text: str) -> int:
        """Cuenta tokens en texto usando tokenizer."""
        if not self.tokenizer:
            # Fallback: aproximación (1 token ≈ 4 chars)
            return len(text) // 4
        
        # TODO: Usar tokenizer real (tiktoken para OpenAI)
        return len(text) // 4
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Divide texto en párrafos."""
        # TODO: Implementar split inteligente
        # - Doble salto de línea
        # - Respeta encabezados markdown
        # - Detecta listas
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return paragraphs
    
    def _apply_overlap(
        self,
        chunks: List[str],
        overlap_tokens: int
    ) -> List[str]:
        """Aplica overlap entre chunks consecutivos."""
        # TODO: Implementar overlap
        # - Tomar últimas overlap_tokens del chunk anterior
        # - Prefijar al siguiente chunk
        return chunks
