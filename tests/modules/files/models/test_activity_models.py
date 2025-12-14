# backend\tests\files\models\test_activity_models..py

# -*- coding: utf-8 -*-
import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.modules.files.enums import ProductFileEvent
from app.modules.files.models.product_file_activity_models import ProductFileActivity

@pytest.mark.asyncio
async def test_product_file_activity_log_minimal(db):
    evt = ProductFileActivity(
        product_file_activity_id=uuid4(),
        product_file_id=uuid4(),
        project_id=uuid4(),
        event_type=ProductFileEvent.generated,
        event_by=uuid4(),
        event_at=datetime.now(timezone.utc),
        product_file_display_name="test.docx",
        product_file_storage_path="project/test.docx",
        product_file_mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        product_file_size_bytes=2048,
        details={"message": "Auto test"},
    )
    db.add(evt)
    await db.commit()
    await db.refresh(evt)
    assert evt.event_type == ProductFileEvent.generated
# Fin del archivo backend\tests\files\models\test_activity_models..py