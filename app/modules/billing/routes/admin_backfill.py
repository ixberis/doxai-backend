# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/routes/admin_backfill.py

Endpoint admin para ejecutar backfill de checkout_intents completados.

Uso:
  POST /api/admin/billing/backfill?limit=500&include_details=false
  POST /api/admin/billing/finalize/{intent_id}

Requiere: require_admin_strict (JWT-based)

Características:
- Chunking por limit/offset para evitar OOM en PROD
- SAVEPOINT por intent para aislamiento de errores
- dry_run para contabilizar sin escribir
- include_details=false por defecto (solo contadores)

Autor: DoxAI
Fecha: 2026-01-14
Updated: 2026-01-14 - Chunking + include_details + dry_run
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.dependency import get_db
from app.modules.auth.dependencies import require_admin_strict
from app.modules.billing.services.finalize_service import BillingFinalizeService
from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/billing", tags=["admin", "billing"])

# ============================================================================
# Response Models
# ============================================================================

class BackfillDetailItem(BaseModel):
    """Detalle de un intent procesado."""
    intent_id: int
    payment_id: Optional[int] = None
    credits_granted: Optional[int] = None
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    result: str  # 'created' | 'already_finalized' | 'failed' | 'skipped_dry_run'
    error: Optional[str] = None


class BackfillErrorSample(BaseModel):
    """Muestra de errores cuando include_details=false."""
    intent_id: int
    error: str


class BackfillResponse(BaseModel):
    """Respuesta del endpoint de backfill."""
    
    success: bool
    dry_run: bool
    processed: int
    created: int
    already_finalized: int
    failed: int
    # Paginación cursor-based (preferido)
    limit: int
    after_intent_id: int  # Cursor usado en esta request
    next_after_intent_id: int  # Cursor para la siguiente página
    has_more: bool
    # Backward compat: offset (deprecated)
    offset: Optional[int] = None
    total_pending: Optional[int] = None  # Solo calculado si offset se usa
    # Detalles (solo si include_details=true)
    details: Optional[List[BackfillDetailItem]] = None
    # Sample de errores (siempre incluido, max 10)
    errors_sample: List[BackfillErrorSample] = []


@dataclass
class BackfillStats:
    """Estadísticas internas del backfill."""
    created: int = 0
    already_finalized: int = 0
    failed: int = 0
    details: List[BackfillDetailItem] = field(default_factory=list)
    errors_sample: List[BackfillErrorSample] = field(default_factory=list)

    def add_error(self, intent_id: int, error: str, max_sample: int = 10):
        """Agrega error al sample (limitado a max_sample)."""
        if len(self.errors_sample) < max_sample:
            self.errors_sample.append(BackfillErrorSample(
                intent_id=intent_id,
                error=error[:200],  # Truncar mensaje largo
            ))


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/backfill",
    response_model=BackfillResponse,
    summary="Backfill checkout intents completados",
    description=(
        "Procesa checkout_intents con status=completed en chunks. "
        "Usa cursor-based pagination (after_intent_id) para paginación determinista. "
        "Usa SAVEPOINT por intent para que un fallo no aborte la corrida."
    ),
    dependencies=[Depends(require_admin_strict)],
)
async def run_backfill(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=500, ge=1, le=5000, description="Máximo de intents a procesar"),
    after_intent_id: int = Query(default=0, ge=0, description="Cursor: procesar intents con id > after_intent_id"),
    offset: Optional[int] = Query(default=None, ge=0, description="DEPRECATED: usar after_intent_id"),
    include_details: bool = Query(default=False, description="Incluir detalles de cada intent"),
    dry_run: bool = Query(default=False, description="Solo contabilizar, no escribir"),
) -> BackfillResponse:
    """
    Ejecuta backfill de checkout_intents completados.
    
    Modos de paginación (mutuamente excluyentes):
    
    1. CURSOR (preferido): usar after_intent_id
       - Query: id > after_intent_id ORDER BY id LIMIT limit
       - has_more = (len(intents) == limit)
       - next_after_intent_id = último id procesado
       
    2. OFFSET (deprecated): usar offset
       - Query: ORDER BY id LIMIT limit OFFSET offset
       - has_more = (offset + limit) < total_pending
       - after_intent_id se ignora (forzado a 0)
    
    Si ambos están presentes: retorna 400 con code=invalid_pagination
    """
    service = BillingFinalizeService()
    stats = BackfillStats()
    
    # =========================================================================
    # Validar modos de paginación mutuamente excluyentes
    # =========================================================================
    use_cursor_mode = offset is None
    use_offset_mode = offset is not None
    
    # Si after_intent_id != 0 Y offset != None => conflicto
    if after_intent_id != 0 and offset is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Cannot combine after_intent_id and offset. Use one or the other.",
                "code": "invalid_pagination",
            },
        )
    
    # =========================================================================
    # Modo OFFSET (deprecated): calcular total_pending, ignorar after_intent_id
    # =========================================================================
    total_pending_value: Optional[int] = None
    effective_after_intent_id = after_intent_id
    
    if use_offset_mode:
        # Forzar cursor a 0 en modo offset
        effective_after_intent_id = 0
        
        # Calcular total_pending para has_more
        count_stmt = select(func.count()).select_from(CheckoutIntent).where(
            CheckoutIntent.status == CheckoutIntentStatus.COMPLETED.value,
        )
        total_result = await db.execute(count_stmt)
        total_pending_value = total_result.scalar_one()
        
        # Query con OFFSET
        stmt = (
            select(CheckoutIntent)
            .where(CheckoutIntent.status == CheckoutIntentStatus.COMPLETED.value)
            .order_by(CheckoutIntent.id)
            .limit(limit)
            .offset(offset)
        )
    else:
        # =====================================================================
        # Modo CURSOR (preferido): id > after_intent_id
        # =====================================================================
        stmt = (
            select(CheckoutIntent)
            .where(
                CheckoutIntent.status == CheckoutIntentStatus.COMPLETED.value,
                CheckoutIntent.id > after_intent_id,
            )
            .order_by(CheckoutIntent.id)
            .limit(limit)
        )
    
    result = await db.execute(stmt)
    intents = result.scalars().all()
    
    # =========================================================================
    # Procesar cada intent con SAVEPOINT
    # =========================================================================
    for intent in intents:
        if dry_run:
            # Solo contabilizar, no escribir
            detail = BackfillDetailItem(
                intent_id=intent.id,
                credits_granted=intent.credits_amount,
                amount_cents=intent.price_cents,
                currency=intent.currency,
                result="skipped_dry_run",
            )
            if include_details:
                stats.details.append(detail)
            stats.created += 1  # Contabilizar como "sería creado"
            continue
        
        try:
            # SAVEPOINT: si falla este intent, no aborta toda la transacción
            async with db.begin_nested():
                finalize_result = await service.finalize_checkout_intent(
                    db,
                    intent.id,
                )
                
                if include_details:
                    stats.details.append(BackfillDetailItem(
                        intent_id=finalize_result.intent_id,
                        payment_id=finalize_result.payment_id,
                        credits_granted=finalize_result.credits_granted,
                        amount_cents=finalize_result.amount_cents,
                        currency=finalize_result.currency,
                        result=finalize_result.result,
                    ))
                
                if finalize_result.result == "created":
                    stats.created += 1
                else:
                    stats.already_finalized += 1
                    
        except Exception as e:
            # Rollback del SAVEPOINT ya ocurrió al salir del context manager
            error_msg = str(e)
            logger.warning(
                "backfill: intent %d failed: %s",
                intent.id,
                error_msg,
            )
            stats.failed += 1
            stats.add_error(intent.id, error_msg)
            
            if include_details:
                stats.details.append(BackfillDetailItem(
                    intent_id=intent.id,
                    result="failed",
                    error=error_msg[:200],
                ))
            # Continuar con el siguiente intent
            continue
    
    # Commit de todos los intents exitosos (solo si no es dry_run)
    if not dry_run:
        await db.commit()
    
    processed = stats.created + stats.already_finalized + stats.failed
    
    # =========================================================================
    # Calcular has_more según el modo
    # =========================================================================
    if use_offset_mode:
        # Modo OFFSET: has_more = (offset + limit) < total_pending
        has_more = (offset + limit) < total_pending_value
    else:
        # Modo CURSOR: has_more = exactamente limit resultados
        has_more = len(intents) == limit
    
    # next_after_intent_id = último id procesado (o el cursor original si no hubo intents)
    next_after_intent_id = intents[-1].id if intents else effective_after_intent_id
    
    logger.info(
        "billing_backfill_completed processed=%d created=%d already_finalized=%d "
        "failed=%d dry_run=%s limit=%d after_intent_id=%d next_after_intent_id=%d "
        "has_more=%s mode=%s",
        processed,
        stats.created,
        stats.already_finalized,
        stats.failed,
        dry_run,
        limit,
        effective_after_intent_id,
        next_after_intent_id,
        has_more,
        "offset" if use_offset_mode else "cursor",
    )
    
    return BackfillResponse(
        success=stats.failed == 0,
        dry_run=dry_run,
        processed=processed,
        created=stats.created,
        already_finalized=stats.already_finalized,
        failed=stats.failed,
        limit=limit,
        after_intent_id=effective_after_intent_id,
        next_after_intent_id=next_after_intent_id,
        has_more=has_more,
        # Solo incluir offset/total_pending en modo offset
        offset=offset if use_offset_mode else None,
        total_pending=total_pending_value if use_offset_mode else None,
        details=stats.details if include_details else None,
        errors_sample=stats.errors_sample,
    )


@router.post(
    "/finalize/{intent_id}",
    response_model=dict,
    summary="Finalizar un checkout intent específico",
    description=(
        "Finaliza un checkout_intent específico por ID. "
        "Crea payment + credit_transaction si no existen."
    ),
    dependencies=[Depends(require_admin_strict)],
)
async def finalize_single_intent(
    intent_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Finaliza un checkout intent específico.
    
    Útil para debugging o procesamiento manual.
    """
    try:
        service = BillingFinalizeService()
        result = await service.finalize_checkout_intent(db, intent_id)
        await db.commit()
        
        logger.info(
            "billing_intent_finalized intent_id=%d payment_id=%d result=%s",
            result.intent_id,
            result.payment_id,
            result.result,
        )
        
        return {
            "success": True,
            "intent_id": result.intent_id,
            "payment_id": result.payment_id,
            "credits_granted": result.credits_granted,
            "amount_cents": result.amount_cents,
            "currency": result.currency,
            "result": result.result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(e), "code": "intent_not_found"},
        )
    except Exception as e:
        logger.exception("Finalize failed for intent %d: %s", intent_id, str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Finalize failed: {str(e)}", "code": "finalize_error"},
        )
