# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/operation/aggregators.py

Agregadores de métricas operativas de Billing.
Consulta v_billing_operation_snapshot para métricas agregadas.

Sin fallback: la vista SQL es la fuente de verdad.

Autor: DoxAI
Fecha: 2026-01-02
"""
import logging
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class OperationSnapshotRow(NamedTuple):
    """Representa una fila de v_billing_operation_snapshot."""
    public_pdf_access_total: int
    public_json_access_total: int
    public_access_total: int
    tokens_expired_total: int
    tokens_not_found_total: int
    tokens_valid_used_total: int
    emails_sent_total: int
    emails_failed_total: int
    pdf_errors_total: int
    http_4xx_errors_total: int
    http_5xx_errors_total: int
    public_access_7d: int
    tokens_expired_7d: int
    emails_failed_7d: int
    http_5xx_errors_7d: int
    generated_at: str


class BillingOperationAggregators:
    """
    Agregadores de métricas operativas de Billing.
    
    Consulta exclusivamente v_billing_operation_snapshot.
    Si la vista no existe o falla, propaga el error.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_billing_operation_snapshot(self) -> OperationSnapshotRow:
        """
        Obtiene snapshot de métricas operativas desde la vista SQL.
        
        Returns:
            OperationSnapshotRow con todas las métricas.
            
        Raises:
            ProgrammingError: Si la vista no existe.
            RuntimeError: Si la vista no retorna datos.
        """
        query = text("""
            SELECT
                public_pdf_access_total,
                public_json_access_total,
                public_access_total,
                tokens_expired_total,
                tokens_not_found_total,
                tokens_valid_used_total,
                emails_sent_total,
                emails_failed_total,
                pdf_errors_total,
                http_4xx_errors_total,
                http_5xx_errors_total,
                public_access_7d,
                tokens_expired_7d,
                emails_failed_7d,
                http_5xx_errors_7d,
                generated_at
            FROM public.v_billing_operation_snapshot
        """)
        
        result = await self.db.execute(query)
        row = result.fetchone()
        
        if not row:
            raise RuntimeError(
                "Métricas operativas no disponibles: "
                "v_billing_operation_snapshot no retorna datos."
            )
        
        return OperationSnapshotRow(
            public_pdf_access_total=int(row[0] or 0),
            public_json_access_total=int(row[1] or 0),
            public_access_total=int(row[2] or 0),
            tokens_expired_total=int(row[3] or 0),
            tokens_not_found_total=int(row[4] or 0),
            tokens_valid_used_total=int(row[5] or 0),
            emails_sent_total=int(row[6] or 0),
            emails_failed_total=int(row[7] or 0),
            pdf_errors_total=int(row[8] or 0),
            http_4xx_errors_total=int(row[9] or 0),
            http_5xx_errors_total=int(row[10] or 0),
            public_access_7d=int(row[11] or 0),
            tokens_expired_7d=int(row[12] or 0),
            emails_failed_7d=int(row[13] or 0),
            http_5xx_errors_7d=int(row[14] or 0),
            generated_at=row[15].isoformat() if row[15] else None,
        )


# Fin del archivo
