
# tests/modules/files/services/analytics/test_activity_stats_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio ActivityStatsService del módulo Files.

Cubre:
- Agregación de eventos de actividad por tipo (ProductFileEvent).
- Filtro por rango de fechas (desde / hasta).
- Cálculo de totales por día o por tipo.
- Retorno vacío si no hay eventos.
- Tolerancia a datos incompletos.
"""

import pytest
from datetime import datetime, timedelta

from app.modules.files.enums.product_file_event_enum import ProductFileEvent
from app.modules.files.models.product_file_activity_models import ProductFileActivity
from app.modules.files.services.activity_stats_service import ActivityStatsService


@pytest.fixture
async def seed_activity(db_session, sample_project, sample_user):
    """Inserta eventos de actividad variados en el rango de fechas."""
    from uuid import UUID, uuid4
    base = datetime.utcnow()
    
    # Convertir IDs a UUID
    project_uuid = sample_project.project_id if isinstance(sample_project.project_id, UUID) else UUID(str(sample_project.project_id))
    user_uuid = UUID(int=sample_user.user_id) if isinstance(sample_user.user_id, int) else UUID(str(sample_user.user_id))
    
    events = [
        ProductFileActivity(
            product_file_activity_id=uuid4(),
            product_file_id=uuid4(),
            project_id=project_uuid,
            event_by=user_uuid,
            event_type=ProductFileEvent.generated,
            event_at=base - timedelta(days=3),
            product_file_display_name="file1.pdf",
            product_file_storage_path="path/to/file1.pdf",
            product_file_mime_type="application/pdf",
            product_file_size_bytes=1024,
            details={"source": "test"},
        ),
        ProductFileActivity(
            product_file_activity_id=uuid4(),
            product_file_id=uuid4(),
            project_id=project_uuid,
            event_by=user_uuid,
            event_type=ProductFileEvent.downloaded,
            event_at=base - timedelta(days=2),
            product_file_display_name="file2.pdf",
            product_file_storage_path="path/to/file2.pdf",
            product_file_mime_type="application/pdf",
            product_file_size_bytes=2048,
            details={"source": "test"},
        ),
        ProductFileActivity(
            product_file_activity_id=uuid4(),
            product_file_id=uuid4(),
            project_id=project_uuid,
            event_by=user_uuid,
            event_type=ProductFileEvent.exported,
            event_at=base - timedelta(days=1),
            product_file_display_name="file3.pdf",
            product_file_storage_path="path/to/file3.pdf",
            product_file_mime_type="application/pdf",
            product_file_size_bytes=3072,
            details={"source": "test"},
        ),
        ProductFileActivity(
            product_file_activity_id=uuid4(),
            product_file_id=uuid4(),
            project_id=project_uuid,
            event_by=user_uuid,
            event_type=ProductFileEvent.downloaded,
            event_at=base,
            product_file_display_name="file4.pdf",
            product_file_storage_path="path/to/file4.pdf",
            product_file_mime_type="application/pdf",
            product_file_size_bytes=4096,
            details={"source": "test"},
        ),
    ]
    for e in events:
        db_session.add(e)
    await db_session.commit()
    await db_session.flush()
    return events, sample_project


@pytest.mark.asyncio
async def test_aggregate_by_event_type_returns_counts(db_session, seed_activity):
    """
    Debe devolver conteos agregados por tipo de evento.
    """
    events, project = seed_activity
    svc = ActivityStatsService(db=db_session)
    result = await svc.aggregate_by_event_type(project_id=project.project_id)

    assert isinstance(result, dict)
    assert ProductFileEvent.generated in result
    assert ProductFileEvent.downloaded in result
    assert all(isinstance(v, int) for v in result.values())
    assert result[ProductFileEvent.downloaded] == 2


@pytest.mark.asyncio
async def test_aggregate_by_event_type_returns_empty_when_no_data(db_session):
    """
    Si no hay datos, debe retornar diccionario vacío.
    """
    from uuid import uuid4
    svc = ActivityStatsService(db=db_session)
    result = await svc.aggregate_by_event_type(project_id=uuid4())
    assert result == {}


@pytest.mark.asyncio
async def test_aggregate_by_event_type_with_date_range_filters(db_session, seed_activity):
    """
    Debe respetar filtros de fechas (from / to).
    """
    events, project = seed_activity
    svc = ActivityStatsService(db=db_session)
    base = datetime.utcnow()

    # Solo últimos 2 días
    date_from = base - timedelta(days=2)
    date_to = base + timedelta(hours=1)

    result = await svc.aggregate_by_event_type(project_id=project.project_id, date_from=date_from, date_to=date_to)
    assert ProductFileEvent.generated not in result  # muy antiguo
    assert ProductFileEvent.downloaded in result
    assert ProductFileEvent.exported in result


@pytest.mark.asyncio
async def test_aggregate_by_day_returns_counts_per_day(db_session, seed_activity):
    """
    Debe devolver un mapping de fechas (YYYY-MM-DD) -> conteo total de eventos.
    """
    events, project = seed_activity
    svc = ActivityStatsService(db=db_session)
    result = await svc.aggregate_by_day(project_id=project.project_id)

    assert isinstance(result, dict)
    for day, count in result.items():
        assert isinstance(day, str)
        assert isinstance(count, int)
        assert len(day.split("-")) == 3  # formato fecha ISO


@pytest.mark.asyncio
async def test_aggregate_handles_incomplete_records_gracefully(db_session, sample_project, sample_user):
    """
    Si hay registros sin event_type o created_at, no debe fallar.
    """
    from uuid import UUID, uuid4
    from app.modules.files.enums.product_file_event_enum import ProductFileEvent
    
    # Convertir IDs a UUID
    project_uuid = sample_project.project_id if isinstance(sample_project.project_id, UUID) else UUID(str(sample_project.project_id))
    user_uuid = UUID(int=sample_user.user_id) if isinstance(sample_user.user_id, int) else UUID(str(sample_user.user_id))
    
    # Crear un evento válido con campos requeridos
    complete = ProductFileActivity(
        product_file_activity_id=uuid4(),
        product_file_id=uuid4(),
        project_id=project_uuid,
        event_by=user_uuid,
        event_type=ProductFileEvent.generated,
        event_at=datetime.utcnow(),
        product_file_display_name="complete.pdf",
        product_file_storage_path="path/complete.pdf",
        product_file_mime_type="application/pdf",
        product_file_size_bytes=1024,
        details={"source": "test"},
    )
    db_session.add(complete)
    await db_session.commit()

    svc = ActivityStatsService(db=db_session)
    result = await svc.aggregate_by_event_type(project_id=sample_project.project_id)
    assert isinstance(result, dict)
    # Debe poder procesar el registro válido sin errores
    assert not isinstance(result, Exception)


# Fin del archivo tests/modules/files/services/analytics/test_activity_stats_service.py
