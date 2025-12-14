
# -*- coding: utf-8 -*-
"""
backend/app/utils/sqlalchemy_typing.py

Utilidades para tipado correcto de instancias SQLAlchemy en consultas .first()

Evita errores de Pylance como:
- "str is not assignable to Column[str]"
- "datetime is not assignable to Column[datetime]"
cuando se accede a atributos de instancias devueltas por .first()

Uso recomendado:
    from app.shared.utils.sqlalchemy_typing import get_instance

    user = get_instance(db.query(User).filter(User.user_email == "example@doxai.ai"), User)
    if user:
        user.is_active = True  # Pylance no se queja

Autor: Ixchel Beristain
Fecha: 31/05/2025
"""

from typing import TypeVar, Type, Optional, cast
from sqlalchemy.orm.query import Query

T = TypeVar("T")

def get_instance(query: Query, model_class: Type[T]) -> Optional[T]:
    """
    Retorna el primer resultado del query, tipado correctamente como instancia del modelo dado.

    Parámetros:
    - query: una consulta SQLAlchemy (ya con filtros aplicados)
    - model_class: la clase del modelo SQLAlchemy, por ejemplo User, PaymentRecord, etc.

    Retorna:
    - None si no hay resultados
    - Una instancia de `model_class` si hay resultados
    """
    result = query.first()
    return cast(Optional[T], query.first())







