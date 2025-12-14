
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/token_issuer_service.py

Servicio responsable de emitir tokens JWT (access / refresh) para usuarios.
Se apoya en los helpers de backend/app/utils/jwt_utils.py, respetando los
TTLs configurados en settings.

Expone:
- create_access_token(sub, extra_claims?)
- issue_tokens_for_user(user_id) -> {access_token, refresh_token}

Autor: Ixchel Beristain
Actualizado: 19/11/2025
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from app.shared.config.config_loader import get_settings
from app.shared.utils.jwt_utils import create_access_token


class TokenIssuerService:
    """
    Servicio de emisión de tokens JWT de aplicación.

    Este servicio centraliza la lógica de:
      - TTL de access token
      - TTL de refresh token
      - Claims mínimos requeridos

    Se mantiene el método create_access_token(...) para compatibilidad con
    código legado, y se añade issue_tokens_for_user(...) para el flujo
    completo access+refresh.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        # Valores por defecto defensivos en caso de que no estén en settings
        self._access_ttl_minutes: int = int(
            getattr(self.settings, "AUTH_ACCESS_TOKEN_TTL_MINUTES", 60)
        )
        self._refresh_ttl_minutes: int = int(
            getattr(self.settings, "AUTH_REFRESH_TOKEN_TTL_MINUTES", 60 * 24 * 7)
        )

    # ---------------------- API legacy ---------------------- #

    def create_access_token(
        self,
        *,
        sub: str,
        extra_claims: Optional[Dict[str, Any]] = None,
        ttl_minutes: Optional[int] = None,
        token_type: str = "access",
    ) -> str:
        """
        Crea un access token (o refresh token, según token_type).

        Args:
            sub: Identificador del sujeto (user_id).
            extra_claims: Claims adicionales a incluir en el token.
            ttl_minutes: TTL en minutos; si es None, se usa el valor por defecto.
            token_type: "access" o "refresh".

        Returns:
            JWT en texto plano.
        """
        data: Dict[str, Any] = {"sub": sub}
        if extra_claims:
            data.update(extra_claims)

        if ttl_minutes is None:
            if token_type == "refresh":
                ttl_minutes = self._refresh_ttl_minutes
            else:
                ttl_minutes = self._access_ttl_minutes

        expires_delta = timedelta(minutes=ttl_minutes)

        # create_access_token es el helper de jwt_utils
        return create_access_token(
            data=data,
            expires_delta=expires_delta,
            token_type=token_type,
        )

    # ---------------------- API nueva ---------------------- #

    def issue_tokens_for_user(self, user_id: str) -> Dict[str, str]:
        """
        Emite un par de tokens (access + refresh) para el usuario.

        Args:
            user_id: Identificador del usuario como string.

        Returns:
            Dict con:
                - access_token
                - refresh_token
        """
        access_token = self.create_access_token(
            sub=user_id,
            token_type="access",
        )
        refresh_token = self.create_access_token(
            sub=user_id,
            token_type="refresh",
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }


__all__ = ["TokenIssuerService"]
# Fin del archivo backend/app/modules/auth/services/token_issuer_service.py