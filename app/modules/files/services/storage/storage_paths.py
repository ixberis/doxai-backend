
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/storage_paths.py

Generador/validador de rutas SSOT para Storage.

SSOT Path Structure (v2):
- Input files:  users/{auth_user_id}/projects/{project_id}/input-files/{file_id}/{storage_name}
- Product files: users/{auth_user_id}/projects/{project_id}/product-files/{file_id}/{storage_name}

El {file_id} como carpeta intermedia evita colisiones de nombres.

Constructor:
    StoragePathsService(base_prefix: str = "")

Autor: Ixchel Beristain
Actualizado: 2026-01-19 (SSOT v2)
"""

import re
from pathlib import PurePosixPath
from typing import Optional
from uuid import UUID

_SAFE_FILENAME_RE = re.compile(r"^[^/\\:*?\"<>|\0]+$")


class StoragePathsService:
    """
    Servicio SSOT para generación de paths de storage.
    
    Estructura canónica:
    - users/{user_id}/projects/{project_id}/input-files/{file_id}/{filename}
    - users/{user_id}/projects/{project_id}/product-files/{file_id}/{filename}
    """
    
    def __init__(self, base_prefix: str = "") -> None:
        self.base_prefix = base_prefix.strip().strip("/")

    @property
    def safe_path_pattern(self):
        """Retorna el regex pattern (como objeto, no como callable)"""
        return _SAFE_FILENAME_RE

    def _join(self, *parts: str) -> str:
        joined = "/".join(p.strip("/") for p in parts if p is not None and p != "")
        return self.normalize(joined)

    def join_path(self, *parts: str) -> str:
        return self._join(*parts)

    def normalize(self, path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path inválido")
        p = PurePosixPath("/" + path.strip().replace("\\", "/"))
        norm = str(p).lstrip("/")
        if ".." in PurePosixPath(norm).parts:
            raise ValueError("path inseguro (..)")
        return norm

    def normalize_path(self, path: str) -> str:
        return self.normalize(path)

    def validate_filename(self, filename: str) -> str:
        """Valida y retorna el filename normalizado."""
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("filename vacío")
        filename = filename.strip()
        if "/" in filename or "\\" in filename:
            raise ValueError("filename no debe contener separadores")
        if not _SAFE_FILENAME_RE.match(filename):
            raise ValueError("filename con caracteres no permitidos")
        return filename

    def ensure_safe_path(self, filename: str) -> None:
        self.validate_filename(filename)

    def split_path(self, path: str) -> list[str]:
        """Divide path en componentes (como lista)"""
        norm = self.normalize(path)
        return [p for p in norm.split("/") if p]

    # -------------------------------------------------------------------------
    # Folder paths (legacy compat)
    # -------------------------------------------------------------------------
    
    def generate_user_folder_path(self, user_id: str | int = None, **kwargs) -> str:
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        path = self._join("users", uid, "")
        if not path.endswith("/"):
            path += "/"
        return path

    def user_folder(self, user_id: str | int = None, **kwargs) -> str:
        return self.generate_user_folder_path(user_id, **kwargs)

    def generate_project_folder_path(self, user_id: str | int = None, project_id: str | int = None, **kwargs) -> str:
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        pid = str(project_id or kwargs.get("project_id", "")).strip()
        path = self._join("users", uid, "projects", pid, "")
        if not path.endswith("/"):
            path += "/"
        return path

    def project_folder(self, user_id: str | int = None, project_id: str | int = None, **kwargs) -> str:
        return self.generate_project_folder_path(user_id, project_id, **kwargs)

    # -------------------------------------------------------------------------
    # SSOT v2: Input file paths con file_id como carpeta
    # -------------------------------------------------------------------------
    
    def generate_input_file_path(
        self,
        user_id: str | int | UUID = None,
        project_id: str | int | UUID = None,
        file_name: str = None,
        file_id: str | UUID = None,
        **kwargs
    ) -> str:
        """
        Genera path SSOT para input file.
        
        SSOT v2: users/{user_id}/projects/{project_id}/input-files/{file_id}/{filename}
        
        Si file_id no se proporciona, usa estructura legacy (sin carpeta file_id).
        """
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        pid = str(project_id or kwargs.get("project_id", "")).strip()
        fid = str(file_id or kwargs.get("file_id", "")).strip() if file_id else ""
        fname = str(file_name or kwargs.get("file_name", "") or kwargs.get("filename", "")).strip()
        
        if fname:
            self.validate_filename(fname)
        
        if fid:
            # SSOT v2: con file_id como carpeta intermedia
            return self._join("users", uid, "projects", pid, "input-files", fid, fname)
        else:
            # Legacy compat: sin file_id (read-only para archivos existentes)
            return self._join("users", uid, "projects", pid, "input", fname)

    def input_file_path(
        self,
        user_id: str | int | UUID = None,
        project_id: str | int | UUID = None,
        file_name: str = None,
        file_id: str | UUID = None,
        **kwargs
    ) -> str:
        return self.generate_input_file_path(user_id, project_id, file_name, file_id, **kwargs)

    # -------------------------------------------------------------------------
    # SSOT v2: Product file paths con file_id como carpeta
    # -------------------------------------------------------------------------
    
    def generate_product_file_path(
        self,
        user_id: str | int | UUID = None,
        project_id: str | int | UUID = None,
        file_name: str = None,
        file_id: str | UUID = None,
        **kwargs
    ) -> str:
        """
        Genera path SSOT para product file.
        
        SSOT v2: users/{user_id}/projects/{project_id}/product-files/{file_id}/{filename}
        
        Si file_id no se proporciona, usa estructura legacy.
        """
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        pid = str(project_id or kwargs.get("project_id", "")).strip()
        fid = str(file_id or kwargs.get("file_id", "")).strip() if file_id else ""
        fname = str(file_name or kwargs.get("file_name", "") or kwargs.get("filename", "")).strip()
        
        if fname:
            self.validate_filename(fname)
        
        if fid:
            # SSOT v2: con file_id como carpeta intermedia
            return self._join("users", uid, "projects", pid, "product-files", fid, fname)
        else:
            # Legacy compat
            return self._join("users", uid, "projects", pid, "output", fname)

    def product_file_path(
        self,
        user_id: str | int | UUID = None,
        project_id: str | int | UUID = None,
        file_name: str = None,
        file_id: str | UUID = None,
        **kwargs
    ) -> str:
        return self.generate_product_file_path(user_id, project_id, file_name, file_id, **kwargs)

    # -------------------------------------------------------------------------
    # Helpers para detectar paths legacy vs SSOT
    # -------------------------------------------------------------------------
    
    # Regex para detectar legacy REAL: {uuid}/input/{filename} o {uuid}/output/{filename}
    # El UUID puede tener formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    _LEGACY_REAL_PATTERN = re.compile(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/(input|output)/[^/]+$",
        re.IGNORECASE
    )
    
    @staticmethod
    def is_ssot_path(path: str) -> bool:
        """
        Detecta si un path sigue la estructura SSOT v2.
        
        SSOT v2 tiene: users/.../input-files/... o users/.../product-files/...
        Legacy tiene: {project_id}/input/... o {project_id}/output/...
        """
        if not path:
            return False
        return "/input-files/" in path or "/product-files/" in path

    @staticmethod
    def is_legacy_path(path: str) -> bool:
        """
        Detecta si un path es legacy (no SSOT v2).
        
        Legacy real de prod: {project_id}/input/{filename}
        """
        return not StoragePathsService.is_ssot_path(path)
    
    @staticmethod
    def is_legacy_real_path(path: str) -> bool:
        """
        Detecta legacy REAL de producción: {uuid}/input/{filename} o {uuid}/output/{filename}
        
        Esta es la estructura actual en prod que NO incluye users/.
        """
        if not path:
            return False
        return bool(StoragePathsService._LEGACY_REAL_PATTERN.match(path))

    # -------------------------------------------------------------------------
    # Helpers para generar keys legacy (lectura de archivos existentes)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def legacy_input_key(project_id: str | UUID, filename: str) -> str:
        """
        Genera key legacy REAL para input files existentes en prod.
        
        Formato: {project_id}/input/{filename}
        
        Usar para descargar archivos legacy sin migración.
        """
        return f"{project_id}/input/{filename}"
    
    @staticmethod
    def legacy_output_key(project_id: str | UUID, filename: str) -> str:
        """
        Genera key legacy REAL para output files existentes en prod.
        
        Formato: {project_id}/output/{filename}
        """
        return f"{project_id}/output/{filename}"

    # -------------------------------------------------------------------------
    # Normalización de storage_name (SSOT)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def normalize_storage_name(filename: str) -> str:
        """
        Normaliza filename para storage.
        
        SSOT Decision: Se mantiene el nombre original (no lowercase) porque:
        - El file_id como carpeta intermedia ya evita colisiones
        - Preservar case ayuda a usuarios a identificar sus archivos
        - Windows es case-insensitive pero Linux no, y file_id nos protege
        
        Solo se limpian caracteres problemáticos para URLs/storage.
        """
        if not filename:
            raise ValueError("filename vacío")
        
        # Trim whitespace
        name = filename.strip()
        
        # Reemplazar caracteres problemáticos para URLs/storage
        # Mantener: letras, números, punto, guión, underscore, espacios
        # Reemplazar otros por guión
        import re
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', name)
        
        # Colapsar múltiples guiones/espacios
        name = re.sub(r'-+', '-', name)
        name = re.sub(r'\s+', ' ', name)
        
        return name.strip('-').strip()


# Singleton para uso en rutas (evita re-instanciar)
_default_paths_service: Optional[StoragePathsService] = None


def get_storage_paths_service() -> StoragePathsService:
    """Retorna singleton de StoragePathsService."""
    global _default_paths_service
    if _default_paths_service is None:
        _default_paths_service = StoragePathsService()
    return _default_paths_service


__all__ = [
    "StoragePathsService",
    "get_storage_paths_service",
]

# Fin del archivo backend/app/modules/files/services/storage/storage_paths.py

