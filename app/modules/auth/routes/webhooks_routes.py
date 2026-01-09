# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/webhooks_routes.py

Rutas de webhooks para el módulo Auth.

Endpoint para recibir webhooks de MailerSend con eventos de entregabilidad.
URL canónica: POST /api/_webhooks/mailersend

Política de respuestas HTTP:
- 200: Webhook procesado (procesado, deduplicado, o evento no mapeado)
- 403: Firma HMAC inválida (seguridad estricta)
- 500: Webhook habilitado en prod/staging sin secret configurado

Características:
- Verificación HMAC SHA256 de firma (header "Signature")
- Idempotencia real via tabla mailersend_webhook_events
- Transiciones de status monotónicas (no regresión)
- DI correcta con Depends(get_db)
- Sanitización de PII en payload raw

Autor: Sistema
Fecha: 2026-01-06
Actualizado: 2026-01-06 - Coherencia HTTP + PII sanitization + fail-fast config
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db

logger = logging.getLogger(__name__)

# Router con prefix /api/_webhooks (será montado en /api)
router = APIRouter(prefix="/_webhooks", tags=["webhooks-auth"])


# ─────────────────────────────────────────────────────────────────
# Status Precedence (para transiciones monotónicas)
# ─────────────────────────────────────────────────────────────────

STATUS_PRECEDENCE = {
    "pending": 0,
    "sent": 1,
    "failed": 1,
    "delivered": 2,
    "bounced": 3,
    "complained": 4,
}


def can_transition(current_status: str, new_status: str) -> bool:
    current_level = STATUS_PRECEDENCE.get(current_status, 0)
    new_level = STATUS_PRECEDENCE.get(new_status, 0)
    return new_level > current_level


# ─────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────

class WebhookConfigurationError(Exception):
    pass


class WebhookConfig:
    _instance: Optional["WebhookConfig"] = None

    def __init__(self):
        self.enabled = self._get_enabled()
        self.signing_secret = self._get_signing_secret()
        self.environment = os.environ.get("ENVIRONMENT", "development").lower()
        self.is_production = self.environment in ("production", "staging", "prod")

        if self.enabled and self.is_production and not self.signing_secret:
            error_msg = (
                "CRITICAL: MAILERSEND_WEBHOOK_ENABLED=1 in production/staging "
                "but MAILERSEND_WEBHOOK_SIGNING_SECRET is not set. "
                "Either disable webhooks or provide the signing secret."
            )
            logger.critical("mailersend_webhook_config_fatal: %s", error_msg)
            raise WebhookConfigurationError(error_msg)

    def _get_enabled(self) -> bool:
        env_val = os.environ.get("MAILERSEND_WEBHOOK_ENABLED", "")
        if env_val:
            return env_val.lower() in ("1", "true", "yes")

        try:
            from app.shared.config import settings
            enabled = getattr(settings, "mailersend_webhook_enabled", False)
            if isinstance(enabled, str):
                return enabled.lower() in ("1", "true", "yes")
            return bool(enabled)
        except ImportError:
            return False

    def _get_signing_secret(self) -> Optional[str]:
        env_val = os.environ.get("MAILERSEND_WEBHOOK_SIGNING_SECRET", "")
        if env_val:
            return env_val

        try:
            from app.shared.config import settings
            secret_value = getattr(settings, "mailersend_webhook_signing_secret", None)
            if secret_value:
                if hasattr(secret_value, "get_secret_value"):
                    return secret_value.get_secret_value()
                return str(secret_value) if secret_value else None
        except ImportError:
            pass

        return None

    @classmethod
    def get(cls) -> "WebhookConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False

    try:
        computed = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature)
    except Exception as e:
        logger.warning("mailersend_webhook_signature_error: %s", str(e))
        return False


# ─────────────────────────────────────────────────────────────────
# MailerSend Event Mapping
# ─────────────────────────────────────────────────────────────────

MAILERSEND_EVENT_STATUS_MAP = {
    "activity.sent": "sent",
    "activity.delivered": "delivered",
    "activity.soft_bounced": "bounced",
    "activity.hard_bounced": "bounced",
    "activity.spam_complaint": "complained",
    "activity.opened": None,
    "activity.clicked": None,
}


# ─────────────────────────────────────────────────────────────────
# Raw Event Storage (Idempotency)
# ─────────────────────────────────────────────────────────────────

def _sanitize_payload_for_storage(payload: dict) -> dict:
    sanitized = json.loads(json.dumps(payload))

    data = sanitized.get("data", {})

    if "recipient" in data:
        recipient = data["recipient"]
        if isinstance(recipient, dict):
            recipient.pop("email", None)
            recipient.pop("name", None)

    if "email" in data and isinstance(data["email"], dict):
        email_data = data["email"]
        if "recipient" in email_data:
            email_data.pop("recipient", None)
        if "to" in email_data:
            email_data.pop("to", None)

    return sanitized


async def _store_raw_event(
    db: AsyncSession,
    event_type: str,
    message_id: str,
    payload: dict,
    signature: Optional[str],
) -> tuple[bool, Optional[int]]:
    sanitized_payload = _sanitize_payload_for_storage(payload)
    sig_prefix = signature[:20] if signature else None

    q = text("""
        INSERT INTO public.mailersend_webhook_events
            (event_type, message_id, payload, signature, process_status)
        VALUES
            (:event_type, :message_id, CAST(:payload AS jsonb), :signature, 'received')
        ON CONFLICT (message_id, event_type) DO NOTHING
        RETURNING id
    """)

    result = await db.execute(q, {
        "event_type": event_type,
        "message_id": message_id,
        "payload": json.dumps(sanitized_payload),
        "signature": sig_prefix,
    })

    row = result.first()
    if row:
        return True, row[0]
    return False, None


async def _update_raw_event_status(
    db: AsyncSession,
    event_id: int,
    status: str,
    error: Optional[str] = None,
) -> None:
    q = text("""
        UPDATE public.mailersend_webhook_events
        SET process_status = :status,
            processed_at = now(),
            error = :error
        WHERE id = :event_id
    """)
    await db.execute(q, {
        "event_id": event_id,
        "status": status,
        "error": error[:500] if error else None,
    })


# ─────────────────────────────────────────────────────────────────
# Process Webhook Event
# ─────────────────────────────────────────────────────────────────

async def _process_webhook_event(
    db: AsyncSession,
    event_type: str,
    message_id: str,
    new_status: str,
    raw_event_id: int,
) -> dict:
    try:
        select_q = text("""
            SELECT event_id, status
            FROM public.auth_email_events
            WHERE provider_message_id = :message_id
            LIMIT 1
        """)

        result = await db.execute(select_q, {"message_id": message_id})
        row = result.first()

        if not row:
            # Antes: "skipped". Ahora: "orphan" (evento válido pero sin match).
            logger.debug(
                "mailersend_webhook_no_matching_event: event_type=%s message_id=%s",
                event_type, message_id
            )
            await _update_raw_event_status(
                db,
                raw_event_id,
                "orphan",
                "no_matching_auth_email_event"
            )
            await db.commit()
            return {"processed": False, "reason": "no_matching_event"}

        event_id, current_status = row[0], row[1]

        if not can_transition(current_status, new_status):
            logger.debug(
                "mailersend_webhook_transition_blocked: message_id=%s current=%s new=%s",
                message_id, current_status, new_status
            )
            await _update_raw_event_status(
                db,
                raw_event_id,
                "skipped",
                f"transition_blocked: {current_status} -> {new_status}",
            )
            await db.commit()
            return {
                "processed": False,
                "reason": "transition_blocked",
                "current_status": current_status,
                "attempted_status": new_status,
            }

        update_q = text("""
            UPDATE public.auth_email_events
            SET status = CAST(:new_status AS public.auth_email_event_status),
                updated_at = now()
            WHERE event_id = :event_id
            RETURNING event_id
        """)

        await db.execute(update_q, {"new_status": new_status, "event_id": event_id})
        await _update_raw_event_status(db, raw_event_id, "processed")
        await db.commit()

        logger.info(
            "mailersend_webhook_event_processed: event_type=%s message_id=%s transition=%s->%s event_id=%s",
            event_type, message_id, current_status, new_status, event_id
        )

        return {
            "processed": True,
            "event_id": str(event_id),
            "action": "updated",
            "transition": f"{current_status} -> {new_status}",
        }

    except Exception as e:
        logger.warning(
            "mailersend_webhook_db_error: event_type=%s message_id=%s error=%s",
            event_type, message_id, str(e)
        )
        await db.rollback()
        try:
            await _update_raw_event_status(db, raw_event_id, "error", str(e))
            await db.commit()
        except Exception:
            pass
        return {"processed": False, "reason": "db_error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────
# Webhook Endpoint
# ─────────────────────────────────────────────────────────────────

@router.post("/mailersend")
async def mailersend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    config = WebhookConfig.get()

    if not config.enabled:
        logger.debug("mailersend_webhook_disabled")
        return {"status": "ok", "processed": False, "reason": "webhook_disabled"}

    body = await request.body()
    signature = request.headers.get("Signature", "")

    if config.signing_secret:
        if not _verify_signature(body, signature, config.signing_secret):
            logger.warning(
                "mailersend_webhook_invalid_signature: signature_prefix=%s",
                signature[:10] if signature else "none"
            )
            raise HTTPException(status_code=403, detail="Invalid signature")
    else:
        if config.is_production:
            logger.error("mailersend_webhook_no_secret_in_production")
            raise HTTPException(status_code=500, detail="Webhook not configured")
        else:
            logger.warning("mailersend_webhook_no_signing_secret_dev_mode")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning("mailersend_webhook_invalid_json: %s", str(e))
        return {"status": "ok", "processed": False, "reason": "invalid_json"}

    event_type = payload.get("type")
    data = payload.get("data", {})

    message_id = (
        data.get("message_id")
        or data.get("email", {}).get("message", {}).get("id")
        or data.get("email", {}).get("id")
        or data.get("email", {}).get("message_id")
    )

    if not event_type:
        logger.debug("mailersend_webhook_no_event_type")
        return {"status": "ok", "processed": False, "reason": "no_event_type"}

    if not message_id:
        logger.warning(
            "mailersend_webhook_no_message_id: event_type=%s has_data=%s",
            event_type, bool(data)
        )
        return {"status": "ok", "processed": False, "reason": "no_message_id"}

    logger.info(
        "mailersend_webhook_received: event_type=%s message_id=%s",
        event_type, message_id
    )

    try:
        is_new, raw_event_id = await _store_raw_event(db, event_type, message_id, payload, signature)
    except Exception as e:
        logger.error("mailersend_webhook_store_error: %s", str(e))
        await db.rollback()
        return {"status": "ok", "processed": False, "reason": "storage_error"}

    if not is_new:
        logger.debug(
            "mailersend_webhook_duplicate: event_type=%s message_id=%s",
            event_type, message_id
        )
        return {"status": "ok", "processed": False, "deduped": True}

    new_status = MAILERSEND_EVENT_STATUS_MAP.get(event_type)

    if new_status is None:
        logger.debug(
            "mailersend_webhook_event_skipped: event_type=%s message_id=%s",
            event_type, message_id
        )
        await _update_raw_event_status(db, raw_event_id, "skipped", "event_not_mapped")
        await db.commit()
        return {"status": "ok", "processed": False, "reason": "event_not_mapped"}

    result = await _process_webhook_event(db, event_type, message_id, new_status, raw_event_id)
    return {"status": "ok", **result}


__all__ = [
    "router",
    "WebhookConfig",
    "WebhookConfigurationError",
    "can_transition",
    "STATUS_PRECEDENCE",
    "_sanitize_payload_for_storage",
]

# Fin del archivo

