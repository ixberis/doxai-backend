# -*- coding: utf-8 -*-
"""
Tests para el servicio de actividad de product files v2.

Cubre:
- log_product_file_event
- list_activity_for_product_file
- list_activity_for_project
"""

import pytest
from uuid import uuid4
from datetime import datetime

from app.modules.files.enums import ProductFileEvent
from app.modules.files.services.product_file_activity.service import (
    log_product_file_event,
    list_activity_for_product_file,
    list_activity_for_project,
)


@pytest.mark.asyncio
async def test_log_product_file_event(db_session):
    """Debe registrar un evento de actividad para un archivo producto."""
    project_id = uuid4()
    product_file_id = uuid4()
    event_by = uuid4()
    
    activity = await log_product_file_event(
        session=db_session,
        project_id=project_id,
        product_file_id=product_file_id,
        event_type=ProductFileEvent.PRODUCT_FILE_GENERATED,
        event_by=event_by,
        snapshot_name="output.pdf",
        snapshot_path="/products/output.pdf",
        snapshot_mime_type="application/pdf",
        snapshot_size_bytes=2048,
        details={"source": "rag_pipeline"},
    )
    
    assert activity is not None
    assert activity.project_id == project_id
    assert activity.product_file_id == product_file_id
    assert activity.event_type == ProductFileEvent.PRODUCT_FILE_GENERATED
    assert activity.event_by == event_by
    assert isinstance(activity.event_at, datetime)


@pytest.mark.asyncio
async def test_list_activity_for_product_file(db_session):
    """Debe listar eventos de un archivo producto."""
    project_id = uuid4()
    product_file_id = uuid4()
    event_by = uuid4()
    
    # Registrar 3 eventos
    for event_type in [
        ProductFileEvent.PRODUCT_FILE_GENERATED,
        ProductFileEvent.PRODUCT_FILE_UPDATED,
        ProductFileEvent.PRODUCT_FILE_DOWNLOADED,
    ]:
        await log_product_file_event(
            session=db_session,
            project_id=project_id,
            product_file_id=product_file_id,
            event_type=event_type,
            event_by=event_by,
        )
    
    await db_session.commit()
    
    activities = await list_activity_for_product_file(
        session=db_session,
        product_file_id=product_file_id,
        limit=100,
    )
    
    assert len(activities) == 3
    event_types = {a.event_type for a in activities}
    assert ProductFileEvent.PRODUCT_FILE_GENERATED in event_types
    assert ProductFileEvent.PRODUCT_FILE_DOWNLOADED in event_types


@pytest.mark.asyncio
async def test_list_activity_for_project(db_session):
    """Debe listar actividad reciente de un proyecto."""
    project_id = uuid4()
    event_by = uuid4()
    
    # Registrar eventos para 2 archivos diferentes
    for i in range(2):
        product_file_id = uuid4()
        await log_product_file_event(
            session=db_session,
            project_id=project_id,
            product_file_id=product_file_id,
            event_type=ProductFileEvent.PRODUCT_FILE_GENERATED,
            event_by=event_by,
            snapshot_name=f"file{i}.pdf",
        )
    
    await db_session.commit()
    
    activities = await list_activity_for_project(
        session=db_session,
        project_id=project_id,
        limit=500,
    )
    
    assert len(activities) == 2
    for a in activities:
        assert a.project_id == project_id


# Fin del archivo
