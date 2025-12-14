# backend/tests/modules/files/services/input_files/storage/conftest.py
# -*- coding: utf-8 -*-
"""
Fixtures para tests de storage que requieren mocks de Supabase.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pydantic import HttpUrl


@pytest.fixture
def mock_settings():
    """Mock de settings con supabase_url para tests de storage."""
    settings = MagicMock()
    settings.supabase_url = HttpUrl("https://test.supabase.co")
    settings.SUPABASE_URL = "https://test.supabase.co"  # Alias por compatibilidad
    settings.supabase_service_role_key = "test-service-role-key"
    settings.supabase_bucket_name = "test-bucket"
    return settings


@pytest.fixture
def mock_supabase_client():
    """Mock del cliente Supabase para tests de storage."""
    client = MagicMock()
    
    # Mock storage bucket operations
    storage = MagicMock()
    bucket = MagicMock()
    
    # Mock upload
    bucket.upload = AsyncMock(return_value={"path": "test/path.txt"})
    
    # Mock download
    bucket.download = AsyncMock(return_value=b"test content")
    
    # Mock list
    bucket.list = AsyncMock(return_value=[
        {"name": "file1.txt", "id": "1", "created_at": "2023-01-01"},
        {"name": "file2.txt", "id": "2", "created_at": "2023-01-02"},
    ])
    
    # Mock remove
    bucket.remove = AsyncMock(return_value={"message": "deleted"})
    
    # Mock move
    bucket.move = AsyncMock(return_value={"message": "moved"})
    
    # Mock create_signed_url
    bucket.create_signed_url = AsyncMock(return_value={
        "signedURL": "https://test.supabase.co/storage/v1/object/sign/test-bucket/file.txt?token=abc123"
    })
    
    storage.from_ = MagicMock(return_value=bucket)
    client.storage = storage
    
    return client
