# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/utils/pdf_receipt_generator.py

Generador de recibos PDF estilo OpenAI para checkouts completados.

Características:
- Layout limpio y comercial (no técnico)
- Invoice number legible
- Secciones: Issuer, Bill to, Line items, Totals, Payment details
- Datos fiscales si existen
- Disclaimer: "No es factura CFDI"
- Fuente Unicode embebida (OpenSans)
- Multiline text support para textos largos (domicilios, razón social)

Autor: DoxAI
Fecha: 2025-12-31
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple

# Importación condicional de ReportLab
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    letter = (612, 792)
    pdfmetrics = None
    TTFont = None
    canvas = None
    HexColor = None


@dataclass
class ReceiptData:
    """Datos básicos del recibo (legacy, para compatibilidad)."""
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


@dataclass
class InvoiceSnapshot:
    """Snapshot completo del invoice para PDF."""
    invoice_number: str
    issued_at: datetime
    paid_at: Optional[datetime]
    issuer: Dict[str, Any]
    bill_to: Dict[str, Any]
    line_items: List[Dict[str, Any]]
    totals: Dict[str, Any]
    payment_details: Dict[str, Any]
    notes: Dict[str, Any] = field(default_factory=dict)


# Registrar fuente Unicode al importar el módulo
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "fonts")
_FONT_PATH = os.path.join(_FONT_DIR, "OpenSans-Regular.ttf")
_FONT_BOLD_PATH = os.path.join(_FONT_DIR, "OpenSans-Bold.ttf")
_FONT_NAME = "DoxAIFont"
_FONT_BOLD_NAME = "DoxAIFontBold"
_FONT_REGISTERED = False


def _ensure_font_registered():
    """Registra las fuentes Unicode si aún no están registradas."""
    global _FONT_REGISTERED
    if not REPORTLAB_AVAILABLE:
        return
    if not _FONT_REGISTERED:
        if os.path.exists(_FONT_PATH):
            pdfmetrics.registerFont(TTFont(_FONT_NAME, _FONT_PATH))
            _FONT_REGISTERED = True
        if os.path.exists(_FONT_BOLD_PATH):
            pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, _FONT_BOLD_PATH))


def _format_price(price_cents: int, currency: str) -> str:
    """Formatea precio en centavos a string legible."""
    price = price_cents / 100
    if currency.upper() == "MXN":
        return f"${price:,.2f} MXN"
    elif currency.upper() == "USD":
        return f"${price:,.2f} USD"
    else:
        return f"{price:,.2f} {currency.upper()}"


def _format_date(dt: datetime) -> str:
    """Formatea fecha a formato legible."""
    return dt.strftime("%d de %B de %Y").replace(
        "January", "enero"
    ).replace(
        "February", "febrero"
    ).replace(
        "March", "marzo"
    ).replace(
        "April", "abril"
    ).replace(
        "May", "mayo"
    ).replace(
        "June", "junio"
    ).replace(
        "July", "julio"
    ).replace(
        "August", "agosto"
    ).replace(
        "September", "septiembre"
    ).replace(
        "October", "octubre"
    ).replace(
        "November", "noviembre"
    ).replace(
        "December", "diciembre"
    )


# Catálogo SAT de regímenes fiscales (clave -> descripción)
SAT_REGIMEN_DESCRIPTIONS = {
    "601": "General de Ley Personas Morales",
    "603": "Personas Morales con Fines no Lucrativos",
    "605": "Sueldos y Salarios e Ingresos Asimilados a Salarios",
    "606": "Arrendamiento",
    "607": "Régimen de Enajenación o Adquisición de Bienes",
    "608": "Demás ingresos",
    "610": "Residentes en el Extranjero sin Establecimiento Permanente en México",
    "611": "Ingresos por Dividendos (socios y accionistas)",
    "612": "Personas Físicas con Actividades Empresariales y Profesionales",
    "614": "Ingresos por intereses",
    "615": "Régimen de los ingresos por obtención de premios",
    "616": "Sin obligaciones fiscales",
    "620": "Sociedades Cooperativas de Producción que optan por diferir sus ingresos",
    "621": "Incorporación Fiscal",
    "622": "Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras",
    "623": "Opcional para Grupos de Sociedades",
    "624": "Coordinados",
    "625": "Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas",
    "626": "Régimen Simplificado de Confianza",
}


def _get_regimen_with_description(clave: str) -> str:
    """
    Devuelve el régimen con su descripción si existe.
    Ejemplo: "612 - Personas Físicas con Actividades Empresariales y Profesionales"
    """
    if not clave:
        return ""
    # Limpiar la clave (puede venir como "612" o ya con descripción)
    clave_limpia = clave.split("-")[0].strip() if "-" in clave else clave.strip()
    descripcion = SAT_REGIMEN_DESCRIPTIONS.get(clave_limpia)
    if descripcion:
        return f"{clave_limpia} - {descripcion}"
    return clave  # Devolver original si no se encuentra


# Colores del tema
COLORS = {
    "primary": HexColor("#1a1a2e") if HexColor else None,
    "secondary": HexColor("#4a4a68") if HexColor else None,
    "accent": HexColor("#0066cc") if HexColor else None,
    "muted": HexColor("#6b7280") if HexColor else None,
    "border": HexColor("#e5e7eb") if HexColor else None,
    "success": HexColor("#10b981") if HexColor else None,
}


def _draw_wrapped_text(c, text: str, x: float, y: float, max_width: float, 
                        font_name: str, font_size: int = 10, 
                        line_height: int = 14) -> float:
    """
    Dibuja texto con wrap automático para evitar sobreposición.
    
    Args:
        c: Canvas de ReportLab
        text: Texto a dibujar
        x: Posición X inicial
        y: Posición Y inicial (top)
        max_width: Ancho máximo permitido
        font_name: Nombre de la fuente
        font_size: Tamaño de fuente
        line_height: Altura de línea
        
    Returns:
        Nueva posición Y después de dibujar
    """
    if not text:
        return y
    
    c.setFont(font_name, font_size)
    
    # Split text into words and wrap
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        if c.stringWidth(test_line, font_name, font_size) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    # Draw each line
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    
    return y


def generate_invoice_pdf(snapshot: InvoiceSnapshot) -> bytes:
    """
    Genera un PDF de recibo estilo OpenAI desde un snapshot.
    
    Args:
        snapshot: Datos del invoice
        
    Returns:
        bytes del PDF generado
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab is not installed")
    
    _ensure_font_registered()
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    font = _FONT_NAME if _FONT_REGISTERED else "Helvetica"
    font_bold = _FONT_BOLD_NAME if _FONT_REGISTERED and os.path.exists(_FONT_BOLD_PATH) else font
    
    margin_left = 50
    margin_right = 50
    content_width = width - margin_left - margin_right
    col_width = (width - margin_left - margin_right - 40) / 2  # Width for each column
    y = height - 50
    
    def draw_text(text: str, x: float, size: int = 10, bold: bool = False, color=None):
        nonlocal y
        c.setFont(font_bold if bold else font, size)
        if color and COLORS.get(color):
            c.setFillColor(COLORS[color])
        else:
            c.setFillColorRGB(0, 0, 0)
        c.drawString(x, y, text)
    
    def draw_right_text(text: str, size: int = 10, bold: bool = False, color=None):
        nonlocal y
        c.setFont(font_bold if bold else font, size)
        if color and COLORS.get(color):
            c.setFillColor(COLORS[color])
        else:
            c.setFillColorRGB(0, 0, 0)
        text_width = c.stringWidth(text, font_bold if bold else font, size)
        c.drawString(width - margin_right - text_width, y, text)
    
    def line_break(amount: float = 16):
        nonlocal y
        y -= amount
    
    def draw_line():
        nonlocal y
        c.setStrokeColor(COLORS["border"] or HexColor("#e5e7eb"))
        c.setLineWidth(0.5)
        c.line(margin_left, y, width - margin_right, y)
        y -= 12
    
    # === HEADER ===
    # Logo / Trade name
    c.setFont(font_bold, 24)
    c.setFillColor(COLORS["primary"] or HexColor("#1a1a2e"))
    c.drawString(margin_left, y, snapshot.issuer.get("trade_name", "DoxAI"))
    
    # Invoice number and date (right side)
    c.setFont(font, 10)
    c.setFillColor(COLORS["muted"] or HexColor("#6b7280"))
    invoice_text = f"Recibo #{snapshot.invoice_number}"
    c.drawRightString(width - margin_right, y, invoice_text)
    y -= 18
    
    date_text = f"Fecha: {_format_date(snapshot.issued_at)}"
    c.drawRightString(width - margin_right, y + 5, date_text)
    
    y -= 30
    draw_line()
    
    # === FROM / TO SECTION ===
    col1_x = margin_left
    col2_x = width / 2 + 20
    
    # Track left and right column y positions separately
    section_y_left = y
    section_y_right = y
    
    # FROM (Issuer) - incluye RFC del emisor
    c.setFont(font_bold, 9)
    c.setFillColor(COLORS["muted"] or HexColor("#6b7280"))
    c.drawString(col1_x, section_y_left, "DE:")
    section_y_left -= 16
    
    c.setFont(font, 10)
    c.setFillColorRGB(0, 0, 0)
    
    # Nombre emisor (con wrap para nombres largos)
    issuer_name = snapshot.issuer.get("name", "")
    if issuer_name:
        section_y_left = _draw_wrapped_text(c, issuer_name, col1_x, section_y_left, col_width, font, 10, 14)
    
    # RFC del emisor
    if snapshot.issuer.get("rfc"):
        c.setFont(font, 10)
        c.drawString(col1_x, section_y_left, f"RFC: {snapshot.issuer['rfc']}")
        section_y_left -= 14
    
    if snapshot.issuer.get("address"):
        addr = snapshot.issuer["address"]
        # Línea 1: calle completa (con wrap)
        addr_line = addr.get("street", "")
        if addr_line:
            c.setFillColorRGB(0, 0, 0)
            section_y_left = _draw_wrapped_text(c, addr_line, col1_x, section_y_left, col_width, font, 10, 14)
        # Línea 2: ciudad, estado, CP, país
        city = addr.get("city", "")
        state = addr.get("state", "")
        zip_code = addr.get("zip", "")
        country = addr.get("country", "")
        parts = [p for p in [city, state, zip_code, country] if p]
        addr_line2 = ", ".join(parts)
        if addr_line2:
            c.setFont(font, 10)
            c.drawString(col1_x, section_y_left, addr_line2)
            section_y_left -= 14
    
    # Email del emisor (con wrap para emails largos)
    if snapshot.issuer.get("email"):
        c.setFillColorRGB(0, 0, 0)
        section_y_left = _draw_wrapped_text(c, snapshot.issuer["email"], col1_x, section_y_left, col_width, font, 10, 14)
    
    # TO (Bill to)
    c.setFont(font_bold, 9)
    c.setFillColor(COLORS["muted"] or HexColor("#6b7280"))
    c.drawString(col2_x, section_y_right, "PARA:")
    section_y_right -= 16
    
    c.setFont(font, 10)
    c.setFillColorRGB(0, 0, 0)
    
    bill_to = snapshot.bill_to
    fiscal = bill_to.get("fiscal") or {}
    
    # Nombre: preferir razon_social fiscal, si no bill_to.name (con wrap)
    name_line = fiscal.get("razon_social") or bill_to.get("name", "")
    if name_line:
        section_y_right = _draw_wrapped_text(c, name_line, col2_x, section_y_right, col_width, font, 10, 14)
    
    # RFC (solo si existe en fiscal)
    if fiscal.get("rfc"):
        c.setFont(font, 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(col2_x, section_y_right, f"RFC: {fiscal['rfc']}")
        section_y_right -= 14
    
    # Domicilio fiscal completo (si existe) - con wrap para direcciones largas
    if fiscal.get("domicilio"):
        c.setFillColorRGB(0, 0, 0)
        section_y_right = _draw_wrapped_text(c, fiscal["domicilio"], col2_x, section_y_right, col_width, font, 10, 14)
    elif fiscal.get("domicilio_cp"):
        c.setFont(font, 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(col2_x, section_y_right, f"C.P.: {fiscal['domicilio_cp']}")
        section_y_right -= 14
    
    # Régimen fiscal (clave + descripción desde catálogo SAT)
    if fiscal.get("regimen_fiscal"):
        c.setFont(font, 10)
        c.setFillColorRGB(0, 0, 0)
        regimen_full = _get_regimen_with_description(fiscal["regimen_fiscal"])
        regimen_text = f"Régimen: {regimen_full}"
        # Usar wrap porque el texto con descripción suele ser largo
        section_y_right = _draw_wrapped_text(c, regimen_text, col2_x, section_y_right, col_width, font, 10, 14)
    
    # Email: preferir fiscal.email, si no bill_to.email (con wrap para emails largos)
    email_line = fiscal.get("email") or bill_to.get("email")
    if email_line:
        c.setFillColorRGB(0, 0, 0)
        section_y_right = _draw_wrapped_text(c, email_line, col2_x, section_y_right, col_width, font, 10, 14)
    
    # Use the lowest y from both columns + adequate padding
    y = min(section_y_left, section_y_right) - 24
    # Ensure minimum spacing before table header (at least 40px from bottom of sections)
    min_table_y = height - 320
    if y > min_table_y:
        y = min_table_y
    draw_line()
    
    # === LINE ITEMS ===
    c.setFont(font_bold, 10)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(margin_left, y, "CONCEPTO")
    c.drawRightString(width - margin_right - 150, y, "CRÉDITOS")
    c.drawRightString(width - margin_right, y, "IMPORTE")
    y -= 16
    
    c.setStrokeColor(COLORS["border"] or HexColor("#e5e7eb"))
    c.setLineWidth(0.5)
    c.line(margin_left, y + 4, width - margin_right, y + 4)
    y -= 8
    
    c.setFont(font, 10)
    for item in snapshot.line_items:
        c.drawString(margin_left, y, item.get("description", ""))
        c.drawRightString(width - margin_right - 150, y, f"{item.get('credits', 0):,}")
        c.drawRightString(width - margin_right, y, _format_price(item.get("total_cents", 0), item.get("currency", "MXN")))
        y -= 18
    
    y -= 10
    draw_line()
    
    # === TOTALS ===
    totals = snapshot.totals
    totals_x = width - margin_right - 200
    
    # Subtotal
    c.setFont(font, 10)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(totals_x, y, "Subtotal:")
    c.drawRightString(width - margin_right, y, totals.get("formatted", {}).get("subtotal", ""))
    y -= 16
    
    # Tax (if any)
    if totals.get("tax_rate", 0) > 0:
        tax_label = f"IVA ({int(totals['tax_rate'] * 100)}%):"
        c.drawString(totals_x, y, tax_label)
        c.drawRightString(width - margin_right, y, totals.get("formatted", {}).get("tax", ""))
        y -= 16
    
    # Total
    c.setFont(font_bold, 12)
    c.drawString(totals_x, y, "Total:")
    c.drawRightString(width - margin_right, y, totals.get("formatted", {}).get("total", ""))
    y -= 20
    
    # Paid badge
    c.setFont(font_bold, 10)
    c.setFillColor(COLORS["success"] or HexColor("#10b981"))
    c.drawString(totals_x, y, "✓ PAGADO")
    c.setFillColorRGB(0, 0, 0)
    c.drawRightString(width - margin_right, y, totals.get("formatted", {}).get("paid", ""))
    
    y -= 40
    draw_line()
    
    # === PAYMENT DETAILS ===
    c.setFont(font_bold, 9)
    c.setFillColor(COLORS["muted"] or HexColor("#6b7280"))
    c.drawString(margin_left, y, "DETALLES DEL PAGO")
    y -= 16
    
    payment = snapshot.payment_details
    c.setFont(font, 9)
    c.setFillColorRGB(0, 0, 0)
    
    if payment.get("provider"):
        c.drawString(margin_left, y, f"Proveedor: {payment['provider']}")
        y -= 14
    
    if payment.get("checkout_intent_id"):
        c.drawString(margin_left, y, f"Referencia: #{payment['checkout_intent_id']}")
        y -= 14
    
    if snapshot.paid_at:
        c.drawString(margin_left, y, f"Fecha de pago: {snapshot.paid_at.strftime('%Y-%m-%d %H:%M UTC')}")
    
    y -= 40
    
    # === DISCLAIMER ===
    c.setStrokeColor(COLORS["border"] or HexColor("#e5e7eb"))
    c.setLineWidth(0.5)
    c.line(margin_left, y + 10, width - margin_right, y + 10)
    y -= 10
    
    c.setFont(font, 8)
    c.setFillColor(COLORS["muted"] or HexColor("#6b7280"))
    
    notes = snapshot.notes
    disclaimer = notes.get("disclaimer", "Este documento es un recibo comercial y no constituye una factura fiscal (CFDI).")
    c.drawString(margin_left, y, disclaimer)
    y -= 12
    
    terms = notes.get("terms", "Los créditos no son reembolsables ni transferibles.")
    c.drawString(margin_left, y, terms)
    y -= 20
    
    # Footer
    c.setFont(font, 8)
    c.drawString(margin_left, y, f"Documento generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    
    # Hash de verificación
    hash_input = f"{snapshot.invoice_number}:{snapshot.payment_details.get('checkout_intent_id', '')}"
    doc_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16].upper()
    c.drawRightString(width - margin_right, y, f"Hash: {doc_hash}")
    
    # Website footer
    y -= 20
    c.setFillColor(COLORS["accent"] or HexColor("#0066cc"))
    c.drawCentredString(width / 2, y, snapshot.issuer.get("website", "https://doxai.site"))
    
    c.showPage()
    c.save()
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


def generate_checkout_receipt_pdf(data: ReceiptData) -> bytes:
    """
    Genera PDF de recibo (legacy - para compatibilidad).
    
    Construye un snapshot básico y llama a generate_invoice_pdf.
    Para nuevos usos, preferir get_or_create_invoice + generate_invoice_pdf.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab is not installed")
    
    # ISSUER_INFO: datos fiscales reales del emisor (persona física)
    ISSUER_INFO = {
        "name": "Ixchel Beristáin Mendoza",
        "trade_name": "DoxAI",
        "rfc": "BEMI720420H72",
        "email": "facturacion@doxai.site",
        "website": "https://doxai.site",
        "address": {
            "street": "Guanajuato 229, Roma Norte, Cuauhtémoc",
            "city": "Ciudad de México",
            "state": "CDMX",
            "zip": "06700",
            "country": "México",
        },
    }
    
    # Construir snapshot básico
    snapshot = InvoiceSnapshot(
        invoice_number=f"DOX-{data.completed_at.year}-{data.checkout_intent_id:04d}",
        issued_at=data.completed_at,
        paid_at=data.completed_at,
        issuer=ISSUER_INFO,
        bill_to={
            "user_id": data.user_id,
            "name": f"Usuario #{data.user_id}",
            "email": None,
        },
        line_items=[
            {
                "description": data.package_name or f"Paquete de créditos ({data.package_id})",
                "quantity": 1,
                "credits": data.credits_amount,
                "total_cents": data.price_cents,
                "currency": data.currency,
            }
        ],
        totals={
            "subtotal_cents": data.price_cents,
            "tax_rate": 0.0,
            "tax_amount_cents": 0,
            "total_cents": data.price_cents,
            "paid_cents": data.price_cents,
            "currency": data.currency,
            "formatted": {
                "subtotal": _format_price(data.price_cents, data.currency),
                "tax": _format_price(0, data.currency),
                "total": _format_price(data.price_cents, data.currency),
                "paid": _format_price(data.price_cents, data.currency),
            },
        },
        payment_details={
            "provider": (data.provider or "").upper(),
            "provider_session_id": data.provider_session_id,
            "checkout_intent_id": data.checkout_intent_id,
        },
        notes={
            "disclaimer": "Este documento es un recibo comercial y no constituye una factura fiscal (CFDI).",
            "terms": "Los créditos no son reembolsables ni transferibles.",
        },
    )
    
    return generate_invoice_pdf(snapshot)


__all__ = [
    "ReceiptData",
    "InvoiceSnapshot",
    "generate_checkout_receipt_pdf",
    "generate_invoice_pdf",
    "REPORTLAB_AVAILABLE",
]
