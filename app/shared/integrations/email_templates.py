# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/email_templates.py

Helper para carga y renderizado de templates de email.
Convención: todos los templates viven en templates/emails/ con nombres *_email.(html|txt).

Autor: Ixchel Beristain
Fecha: 2025-12-15
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Directorio canónico de templates
EMAILS_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"


def get_emails_dir() -> Path:
    """Retorna el directorio canónico de templates de email."""
    return EMAILS_DIR


def load_template(template_name: str) -> Optional[str]:
    """
    Carga template desde templates/emails/.
    
    Args:
        template_name: Nombre del archivo (ej: "activation_email.html")
    
    Returns:
        Contenido del template o None si no existe.
    """
    path = EMAILS_DIR / template_name
    if path.exists():
        try:
            content = path.read_text(encoding="utf-8")
            logger.debug("[EmailTemplates] loaded: %s", template_name)
            return content
        except Exception as e:
            logger.warning("[EmailTemplates] error reading %s: %s", template_name, e)
    else:
        logger.debug("[EmailTemplates] not found: %s", template_name)
    return None


def render_template(raw: str, context: Dict[str, Any]) -> str:
    """
    Renderiza template reemplazando placeholders {{ variable }} y {{variable}}.
    """
    result = raw
    for key, value in context.items():
        result = result.replace(f"{{{{ {key} }}}}", str(value))
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def render_email(
    template_base: str,
    context: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Renderiza email completo (HTML y texto) desde templates/emails/.
    
    Args:
        template_base: Nombre base (ej: "activation_email" -> activation_email.html/txt)
        context: Variables a sustituir
    
    Returns:
        (html, text, used_template) - html/text pueden ser None si no hay template
    """
    html_name = f"{template_base}.html"
    txt_name = f"{template_base}.txt"

    html_content = load_template(html_name)
    txt_content = load_template(txt_name)

    used_template = html_content is not None

    html = render_template(html_content, context) if html_content else None
    text = render_template(txt_content, context) if txt_content else None

    if used_template:
        logger.info("[EmailTemplates] rendered: %s", template_base)
    else:
        logger.debug("[EmailTemplates] no template for: %s", template_base)

    return html, text, used_template


def mask_token(token: str) -> str:
    """Enmascara token para logging seguro (primeros 4 + últimos 4)."""
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


# Fallbacks de texto plano mínimos (sin HTML)
FALLBACK_ACTIVATION_TEXT = """Estimado/a {user_name},

Gracias por registrarse en DoxAI. Para activar su cuenta, visite:
{activation_link}

Este enlace expirará en 60 minutos.

Si no solicitó esta cuenta, ignore este mensaje.

Atentamente,
El equipo de DoxAI
"""

FALLBACK_PASSWORD_RESET_TEXT = """Hola {user_name},

Recibimos una solicitud para restablecer su contraseña. Visite:
{reset_link}

Este enlace expirará en 60 minutos.

Si no solicitó este cambio, ignore este mensaje.

Atentamente,
El equipo de DoxAI
"""

FALLBACK_WELCOME_TEXT = """Estimado/a {user_name},

¡Bienvenido a DoxAI! Su cuenta ha sido activada exitosamente.

Se le han asignado {credits_assigned} créditos gratuitos.

Inicie sesión aquí: {frontend_url}

Gracias por elegir DoxAI.

Atentamente,
El equipo de DoxAI
"""

FALLBACK_NO_LINK_TEXT = """Estimado/a {user_name},

Gracias por registrarse en DoxAI. Por favor contacte a soporte para completar la activación de su cuenta.

Atentamente,
El equipo de DoxAI
"""


def get_fallback_text(email_type: str, context: Dict[str, Any]) -> str:
    """
    Obtiene texto de fallback mínimo para cuando no hay templates.
    """
    templates = {
        "activation": FALLBACK_ACTIVATION_TEXT,
        "password_reset": FALLBACK_PASSWORD_RESET_TEXT,
        "welcome": FALLBACK_WELCOME_TEXT,
        "activation_no_link": FALLBACK_NO_LINK_TEXT,
    }
    
    template = templates.get(email_type, FALLBACK_NO_LINK_TEXT)
    
    try:
        return template.format(**context)
    except KeyError:
        return template


__all__ = [
    "get_emails_dir",
    "load_template",
    "render_template",
    "render_email",
    "mask_token",
    "get_fallback_text",
]
