
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/storage_paths.py

Generador/validador de rutas ‘lógicas’ de storage, con normalización y
validación de nombres de archivo.

Constructor sin parámetros (tests instancian simple):
    StoragePathsService()

API esperada por tests (mínimo):
    - generate_user_folder_path(user_id: str) -> str
    - generate_project_folder_path(project_id: str) -> str
    - generate_input_file_path(project_id: str, filename: str) -> str
    - generate_product_file_path(project_id: str, filename: str) -> str
    - normalize(path: str) -> str
    - validate_filename(filename: str) -> None (raise ValueError si inválido)

Generador/validador de rutas lógicas de storage, con normalización y validación.

Constructor (según tests):
    StoragePathsService(base_prefix: str = "")

Autor: Ixchel Beristain
Fecha 04/11/2025
"""

import re
from pathlib import PurePosixPath

_SAFE_FILENAME_RE = re.compile(r"^[^/\\:*?\"<>|\0]+$")


class StoragePathsService:
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

    def generate_input_file_path(self, user_id: str | int = None, project_id: str | int = None, file_name: str = None, **kwargs) -> str:
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        pid = str(project_id or kwargs.get("project_id", "")).strip()
        fname = str(file_name or kwargs.get("file_name", "") or kwargs.get("filename", "")).strip()
        if fname:
            self.validate_filename(fname)
        return self._join("users", uid, "projects", pid, "input", fname)

    def input_file_path(self, user_id: str | int = None, project_id: str | int = None, file_name: str = None, **kwargs) -> str:
        return self.generate_input_file_path(user_id, project_id, file_name, **kwargs)

    def generate_product_file_path(self, user_id: str | int = None, project_id: str | int = None, file_name: str = None, **kwargs) -> str:
        uid = str(user_id or kwargs.get("user_id", "")).strip()
        pid = str(project_id or kwargs.get("project_id", "")).strip()
        fname = str(file_name or kwargs.get("file_name", "") or kwargs.get("filename", "")).strip()
        if fname:
            self.validate_filename(fname)
        return self._join("users", uid, "projects", pid, "output", fname)

    def product_file_path(self, user_id: str | int = None, project_id: str | int = None, file_name: str = None, **kwargs) -> str:
        return self.generate_product_file_path(user_id, project_id, file_name, **kwargs)

# Fin del archivo backend\app\modules\files\services\storage\storage_paths.py





