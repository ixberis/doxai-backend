
# backend/app/services/embedding/embedding_validator_service.py

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.modules.files.enums import FileCategory
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile


def validate_file_origin(db: Session, file_id: UUID, file_origin: FileCategory) -> None:
    """
    Verifica que el file_id exista en la tabla correcta según el origen declarado (input_file o product_file).
    Lanza HTTP 400 si no corresponde.
    """
    if file_origin == FileCategory.INPUT_FILE:
        file_exists = db.query(InputFile).filter(InputFile.input_file_id == file_id).first()
        if not file_exists:
            raise HTTPException(status_code=400, detail="El archivo no existe en input_files, pero el origen es 'input_file'.")

    elif file_origin == FileCategory.PRODUCT_FILE:
        file_exists = db.query(ProductFile).filter(ProductFile.input_file_id == file_id).first()
        if not file_exists:
            raise HTTPException(status_code=400, detail="El archivo no existe en product_files, pero el origen es 'product_file'.")

    else:
        raise HTTPException(status_code=400, detail=f"Origen de archivo inválido: {file_origin}")







