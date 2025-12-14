# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/ocr/routes_ocr_callbacks.py

Ruteadores para callbacks/webhooks del proveedor OCR en el módulo RAG.

Implementación mínima:
- Endpoint POST /rag/ocr/callbacks/azure
- Registra el callback en la tabla ocr_callbacks con:
    * ocr_request_id
    * event
    * payload serializado
    * hash SHA-256 del payload

La lógica detallada de actualización de ocr_requests y pipeline podrá
implementarse posteriormente desde facades especializados.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import json
import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.shared.database.database import get_db

router = APIRouter(tags=["RAG OCR Callbacks"])


class AzureOcrCallbackPayload(BaseModel):
    """
    Payload genérico para callbacks de Azure OCR.

    Campos mínimos requeridos:
    - ocr_request_id: vincula el callback con la solicitud OCR interna.
    - event: estado del callback (received, validated, completed, failed).
    - data: payload original del proveedor (estructura libre).
    """

    ocr_request_id: UUID = Field(..., description="ID de la solicitud OCR interna.")
    event: str = Field(..., description="Evento del callback (received/completed/failed).")
    data: dict = Field(default_factory=dict, description="Payload libre de Azure OCR.")


@router.post(
    "/rag/ocr/callbacks/azure",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Callback Azure OCR",
)
async def azure_ocr_callback(
    payload: AzureOcrCallbackPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Recibe callbacks desde Azure OCR y los registra en `ocr_callbacks`.

    Esta implementación:
    - Serializa el payload completo.
    - Calcula su hash SHA-256.
    - Inserta un registro en ocr_callbacks con el evento indicado.

    La actualización de ocr_requests/ocr_pages/ocr_billing puede delegarse a
    servicios/facades especializados posteriormente.
    """
    payload_bytes = json.dumps(payload.data, ensure_ascii=False).encode("utf-8")
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

    result = await db.execute(
        text(
            """
            INSERT INTO ocr_callbacks (
                ocr_request_id,
                event,
                payload_enc,
                payload_sha256
            )
            VALUES (
                :ocr_request_id,
                :event,
                :payload_enc,
                :payload_sha256
            )
            RETURNING callback_id
            """
        ),
        {
            "ocr_request_id": str(payload.ocr_request_id),
            "event": payload.event,
            "payload_enc": payload_bytes,
            "payload_sha256": payload_sha256,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar el callback de Azure OCR.",
        )

    await db.commit()
    return {"status": "accepted", "callback_id": str(row["callback_id"])}


# Fin del archivo backend/app/modules/rag/routes/ocr/routes_ocr_callbacks.py
