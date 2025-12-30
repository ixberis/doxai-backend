# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/utils/pdf_receipt_generator.py

Generador de recibos PDF para checkouts completados.

Utiliza ReportLab con fuente Unicode embebida para renderizar
correctamente caracteres españoles (áéíóú ñ ¿¡).

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

# Importación condicional de ReportLab para evitar fallos en tests sin la dependencia
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    letter = (612, 792)  # Fallback page size
    pdfmetrics = None
    TTFont = None
    canvas = None


@dataclass
class ReceiptData:
    """Datos necesarios para generar un recibo PDF."""
    checkout_intent_id: int
    user_id: int
    credits_amount: int
    price_cents: int
    currency: str
    provider: Optional[str]
    provider_session_id: Optional[str]
    package_id: Optional[str]
    package_name: Optional[str]
    created_at: datetime
    completed_at: datetime


# Registrar fuente Unicode al importar el módulo
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "fonts")
_FONT_PATH = os.path.join(_FONT_DIR, "OpenSans-Regular.ttf")
_FONT_NAME = "DoxAIFont"
_FONT_REGISTERED = False


def _ensure_font_registered():
    """Registra la fuente Unicode si aún no está registrada."""
    global _FONT_REGISTERED
    if not REPORTLAB_AVAILABLE:
        return
    if not _FONT_REGISTERED:
        if os.path.exists(_FONT_PATH):
            pdfmetrics.registerFont(TTFont(_FONT_NAME, _FONT_PATH))
            _FONT_REGISTERED = True
        else:
            # Fallback: usar Helvetica (built-in, sin soporte completo Unicode)
            pass


def _format_price(price_cents: int, currency: str) -> str:
    """Formatea precio en centavos a string legible."""
    price = price_cents / 100
    if currency == "MXN":
        return f"${price:,.2f} MXN"
    elif currency == "USD":
        return f"${price:,.2f} USD"
    else:
        return f"{price:,.2f} {currency}"


def generate_checkout_receipt_pdf(data: ReceiptData) -> bytes:
    """
    Genera un PDF de recibo para un checkout completado.
    
    Args:
        data: Datos del recibo a generar
        
    Returns:
        bytes del PDF generado
        
    Raises:
        RuntimeError: Si ReportLab no está instalado
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "ReportLab is not installed. Install it with: pip install reportlab"
        )
    
    _ensure_font_registered()
    
    # Formatear datos
    price_formatted = _format_price(data.price_cents, data.currency)
    completed_str = data.completed_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    generated_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    package_display = data.package_name or data.package_id or "N/A"
    provider_display = (data.provider or "N/A").upper()
    session_display = data.provider_session_id or "N/A"
    
    # Generar hash de verificación
    hash_input = f"{data.checkout_intent_id}:{data.user_id}:{data.credits_amount}:{completed_str}"
    doc_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16].upper()
    
    # Idempotency key
    idempotency_key = f"checkout_intent_{data.checkout_intent_id}"
    
    # Crear PDF en memoria
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter  # 612 x 792 puntos
    
    # Configurar fuente
    font_name = _FONT_NAME if _FONT_REGISTERED else "Helvetica"
    
    # Posición inicial
    y = height - 50
    line_height = 16
    left_margin = 50
    
    def draw_line(text: str, bold: bool = False, size: int = 11):
        """Dibuja una línea de texto y avanza Y."""
        nonlocal y
        if bold:
            c.setFont(f"{font_name}", size + 1)
        else:
            c.setFont(font_name, size)
        c.drawString(left_margin, y, text)
        y -= line_height
    
    def draw_separator():
        """Dibuja una línea separadora."""
        nonlocal y
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.line(left_margin, y + 5, width - left_margin, y + 5)
        y -= line_height
    
    # === ENCABEZADO ===
    c.setFont(font_name, 16)
    c.drawString(left_margin, y, "Recibo de compra de créditos")
    y -= 24
    
    c.setFont(font_name, 10)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(left_margin, y, "Documento generado electrónicamente")
    y -= line_height
    
    c.setFillColorRGB(0, 0.4, 0.8)
    c.drawString(left_margin, y, "https://doxai.site")
    y -= line_height * 2
    
    c.setFillColorRGB(0, 0, 0)
    draw_line(f"Fecha de emisión: {generated_str}")
    y -= line_height
    
    # === DATOS DEL CLIENTE ===
    draw_separator()
    c.setFont(font_name, 12)
    c.drawString(left_margin, y, "DATOS DEL CLIENTE")
    y -= line_height + 4
    
    draw_line(f"User ID: {data.user_id}")
    y -= line_height
    
    # === DETALLES DE LA TRANSACCIÓN ===
    draw_separator()
    c.setFont(font_name, 12)
    c.drawString(left_margin, y, "DETALLES DE LA TRANSACCIÓN")
    y -= line_height + 4
    
    draw_line(f"Checkout Intent ID: {data.checkout_intent_id}")
    draw_line("Estado: COMPLETED")
    draw_line(f"Fecha de pago: {completed_str}")
    draw_line(f"Proveedor de pago: {provider_display}")
    draw_line(f"Session ID: {session_display}")
    y -= 4
    draw_line(f"Moneda: {data.currency}")
    draw_line(f"Importe pagado: {price_formatted}")
    y -= line_height
    
    # === PAQUETE ADQUIRIDO ===
    draw_separator()
    c.setFont(font_name, 12)
    c.drawString(left_margin, y, "PAQUETE ADQUIRIDO")
    y -= line_height + 4
    
    draw_line(f"Paquete: {package_display}")
    draw_line(f"Créditos acreditados: {data.credits_amount:,}")
    y -= line_height
    
    # === INFORMACIÓN DE AUDITORÍA ===
    draw_separator()
    c.setFont(font_name, 12)
    c.drawString(left_margin, y, "INFORMACIÓN DE AUDITORÍA")
    y -= line_height + 4
    
    draw_line("Los créditos fueron acreditados de forma idempotente")
    draw_line("al monedero del usuario conforme al ledger interno de DoxAI.")
    y -= 4
    draw_line(f"Idempotency Key: {idempotency_key}")
    y -= line_height
    
    # === AVISO LEGAL ===
    draw_separator()
    c.setFont(font_name, 12)
    c.drawString(left_margin, y, "AVISO LEGAL")
    y -= line_height + 4
    
    c.setFont(font_name, 9)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(left_margin, y, "Este recibo no constituye una factura fiscal. Para efectos fiscales")
    y -= 14
    c.drawString(left_margin, y, "consulte a su proveedor autorizado.")
    y -= line_height * 2
    
    c.setFillColorRGB(0, 0, 0)
    draw_line(f"Documento generado: {generated_str}", size=9)
    draw_line(f"Hash de verificación: {doc_hash}", size=9)
    
    # Finalizar PDF
    c.showPage()
    c.save()
    
    # Obtener bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


__all__ = [
    "ReceiptData",
    "generate_checkout_receipt_pdf",
    "REPORTLAB_AVAILABLE",
]
