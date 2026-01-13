# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/operation/routes.py

Rutas internas de métricas operativas para Admin → Billing → Operación.

Expone endpoints JSON de monitoreo técnico:
- /_internal/admin/billing/operation/summary: snapshot de métricas operativas

Sin fallback: la fuente de verdad es solo v_billing_operation_snapshot.
Si la vista falla, responde 500.

Autor: DoxAI
Fecha: 2026-01-02
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from .schemas import BillingOperationSnapshot
from .aggregators import BillingOperationAggregators


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/admin/billing/operation",
    tags=["admin-billing-operation"],
    dependencies=[Depends(require_admin_strict)],
)


def _compute_rate(numerator: int, denominator: int) -> float:
    """Calcula ratio evitando división por cero."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


@router.get("/summary", response_model=BillingOperationSnapshot)
async def get_billing_operation_summary(db: AsyncSession = Depends(get_db)):
    """
    Devuelve un snapshot JSON con métricas operativas agregadas.
    
    Fuente de verdad: v_billing_operation_snapshot (1 query).
    Sin fallback: si la vista no existe, responde 500.
    
    Campos:
    - public_*: accesos a recibos públicos
    - tokens_*: uso de tokens públicos
    - emails_*: métricas de envío de emails
    - *_errors_*: conteos de errores
    - generated_at
    
    Sin PII. Orientado a diagnóstico técnico.
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[billing_operation_summary:{request_id}] Request started")
    
    agg = BillingOperationAggregators(db)
    
    try:
        snapshot = await agg.get_billing_operation_snapshot()
        
        # Calcular ratios derivados
        total_token_attempts = (
            snapshot.tokens_valid_used_total + 
            snapshot.tokens_expired_total + 
            snapshot.tokens_not_found_total
        )
        token_expiry_rate = _compute_rate(
            snapshot.tokens_expired_total,
            total_token_attempts
        )
        
        total_emails = snapshot.emails_sent_total + snapshot.emails_failed_total
        email_failure_rate = _compute_rate(
            snapshot.emails_failed_total,
            total_emails
        )
        
        logger.info(
            f"[billing_operation_summary:{request_id}] source=db_view "
            f"public_access={snapshot.public_access_total} "
            f"tokens_expired={snapshot.tokens_expired_total} "
            f"emails_failed={snapshot.emails_failed_total} "
            f"5xx_errors={snapshot.http_5xx_errors_total}"
        )
        
        return BillingOperationSnapshot(
            # Recibos públicos
            public_pdf_access_total=snapshot.public_pdf_access_total,
            public_json_access_total=snapshot.public_json_access_total,
            public_access_total=snapshot.public_access_total,
            public_access_7d=snapshot.public_access_7d,
            
            # Tokens
            tokens_valid_used_total=snapshot.tokens_valid_used_total,
            tokens_expired_total=snapshot.tokens_expired_total,
            tokens_not_found_total=snapshot.tokens_not_found_total,
            tokens_expired_7d=snapshot.tokens_expired_7d,
            token_expiry_rate=token_expiry_rate,
            
            # Emails
            emails_sent_total=snapshot.emails_sent_total,
            emails_failed_total=snapshot.emails_failed_total,
            emails_failed_7d=snapshot.emails_failed_7d,
            email_failure_rate=email_failure_rate,
            
            # Errores
            pdf_errors_total=snapshot.pdf_errors_total,
            http_4xx_errors_total=snapshot.http_4xx_errors_total,
            http_5xx_errors_total=snapshot.http_5xx_errors_total,
            http_5xx_errors_7d=snapshot.http_5xx_errors_7d,
            
            # Meta
            generated_at=snapshot.generated_at,
        )
        
    except ProgrammingError as e:
        # Vista SQL no existe (error de Postgres)
        logger.error(f"[billing_operation_summary:{request_id}] Vista SQL no existe: {e}")
        raise HTTPException(
            status_code=500,
            detail="Métricas operativas no disponibles: falta vista SQL / migración de v_billing_operation_snapshot.",
        )
        
    except RuntimeError as e:
        # Vista existe pero no retorna datos
        logger.error(f"[billing_operation_summary:{request_id}] {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
        
    except Exception as e:
        logger.exception(f"[billing_operation_summary:{request_id}] Error inesperado: {e}")
        raise HTTPException(
            status_code=500,
            detail="Métricas operativas no disponibles: error interno.",
        )


# Fin del archivo
