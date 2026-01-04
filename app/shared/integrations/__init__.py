# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/__init__.py

Clientes de integración con servicios externos.
"""

from .azure_document_intelligence import AzureDocumentIntelligenceClient, AzureOcrResult
from .openai_embeddings_client import generate_embeddings
from .azure_types import (
    AzureAnalysisStatus,
    AzureModelId,
    AzureDocumentResult,
    AzurePage,
    AzureConfig,
)

# Email senders
from .email_sender import (
    IEmailSender,
    EmailSender,
    StubEmailSender,
    get_email_sender,
)
from .smtp_email_sender import SMTPEmailSender
from .mailersend_email_sender import MailerSendEmailSender, MailerSendError

__all__ = [
    # Azure
    "AzureDocumentIntelligenceClient",
    "AzureOcrResult",
    "AzureAnalysisStatus",
    "AzureModelId",
    "AzureDocumentResult",
    "AzurePage",
    "AzureConfig",
    # OpenAI
    "generate_embeddings",
    # Email
    "IEmailSender",
    "EmailSender",
    "StubEmailSender",
    "SMTPEmailSender",
    "MailerSendEmailSender",
    "MailerSendError",
    "get_email_sender",
]
