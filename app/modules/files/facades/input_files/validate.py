
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/input_files/validate.py

Validaciones para archivos de entrada.
Código puro sin dependencias de DB/FastAPI para facilitar testing.

Alineación:
- Se usa un mapeo derivado del enum FileType para validar extensiones.
- DEFAULT_ALLOWED_EXTENSIONS se deriva del mapeo, con fallback configurable.
- Modo estricto de MIME: compara tipo completo y/o familia (image/, audio/, etc.).

Autor: Ixchel Beristain
Fecha: 2025-11-10
"""

import logging
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Set, Iterable

from app.modules.files.enums import FileType
from app.modules.files.facades.errors import InvalidFileType, FileValidationError

logger = logging.getLogger(__name__)

# ------------------------- mapeos y utilidades -------------------------

# Cobertura amplia, alineada con FileType y formatos comunes en la plataforma
_TYPE_EXTENSIONS_MAP: Dict[FileType, Set[str]] = {
    # Documentos y texto
    FileType.pdf:  {".pdf"},
    FileType.docx: {".docx", ".doc"},
    FileType.xlsx: {".xlsx", ".xls"},
    FileType.pptx: {".pptx", ".ppt"},
    FileType.txt:  {".txt"},
    FileType.csv:  {".csv"},
    FileType.md:   {".md", ".markdown"},
    FileType.rtf:  {".rtf"},
    FileType.html: {".html", ".htm"},
    FileType.json: {".json"},
    FileType.xml:  {".xml"},

    # Medios
    FileType.image: {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"},
    FileType.video: {".mp4", ".mov", ".avi", ".wmv", ".flv", ".mkv", ".webm", ".mpeg", ".mpg"},
    FileType.audio: {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"},

    # Contenedores/paquetes
    FileType.zip: {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"},
}


def _all_allowed_extensions_from_enum() -> Set[str]:
    """Unión de todas las extensiones del mapeo."""
    all_exts: Set[str] = set()
    for exts in _TYPE_EXTENSIONS_MAP.values():
        all_exts.update(exts)
    return all_exts


# Fallback configurable (en caso de necesitar override externo)
DEFAULT_MAX_FILE_SIZE_MB = 500
DEFAULT_ALLOWED_EXTENSIONS = _all_allowed_extensions_from_enum()

# ------------------------------ validaciones ------------------------------

def validate_file_type_consistency(
    filename: str,
    file_type: FileType,
    mime_type: str,
    strict: bool = False
) -> None:
    """
    Valida consistencia entre nombre de archivo, FileType declarado y MIME type.

    Args:
        filename: Nombre del archivo
        file_type: Tipo declarado del archivo (enum FileType)
        mime_type: MIME type del archivo (p.ej., 'application/pdf', 'image/png')
        strict: Si True, valida MIME con mayor exigencia

    Raises:
        InvalidFileType: Si hay inconsistencias
    """
    ext = Path(filename).suffix.lower()
    expected_extensions = _TYPE_EXTENSIONS_MAP.get(file_type, set())

    # 1) Extensión vs FileType declarado
    if expected_extensions and ext not in expected_extensions:
        raise InvalidFileType(
            f"Extensión '{ext}' no coincide con tipo declarado '{file_type.value}'. "
            f"Extensiones esperadas: {', '.join(sorted(expected_extensions))}"
        )

    # 2) MIME estricto (opcional): compara tipo completo o familia
    #    - guess_type puede devolver None; si es None, no forzamos error.
    if strict:
        guessed_mime, _ = mimetypes.guess_type(filename)
        if guessed_mime:
            # Coincidencia exacta o por familia (image/, audio/, etc.)
            if (guessed_mime != mime_type) and (
                guessed_mime.split("/", 1)[0] != mime_type.split("/", 1)[0]
            ):
                logger.warning(
                    "mime_type_mismatch",
                    extra={
                        "filename": filename,
                        "declared_mime": mime_type,
                        "guessed_mime": guessed_mime,
                    },
                )
                raise InvalidFileType(
                    f"MIME inconsistente: declarado '{mime_type}', detectado '{guessed_mime}'"
                )


def validate_file_size(
    size_bytes: int,
    max_size_mb: Optional[int] = None
) -> None:
    """
    Valida que el tamaño del archivo esté dentro de límites permitidos.

    Args:
        size_bytes: Tamaño del archivo en bytes
        max_size_mb: Tamaño máximo permitido en MB (usa default si None)

    Raises:
        FileValidationError: Si el tamaño excede el límite o es inválido
    """
    max_mb = max_size_mb or DEFAULT_MAX_FILE_SIZE_MB
    max_bytes = max_mb * 1024 * 1024

    if size_bytes > max_bytes:
        raise FileValidationError(
            f"Archivo excede tamaño máximo permitido: "
            f"{size_bytes / (1024*1024):.2f} MB > {max_mb} MB"
        )

    if size_bytes <= 0:
        raise FileValidationError("Tamaño de archivo inválido: debe ser mayor a 0 bytes")


def validate_filename_extension(
    filename: str,
    allowed_extensions: Optional[Iterable[str]] = None
) -> None:
    """
    Valida que la extensión del archivo esté permitida.

    Args:
        filename: Nombre del archivo
        allowed_extensions: Iterable de extensiones permitidas (usa derivadas del enum si None)

    Raises:
        InvalidFileType: Si la extensión no está permitida
    """
    allowed_set: Set[str] = set(allowed_extensions) if allowed_extensions else DEFAULT_ALLOWED_EXTENSIONS
    ext = Path(filename).suffix.lower()

    if not ext:
        raise InvalidFileType(f"Archivo sin extensión: {filename}")

    if ext not in allowed_set:
        raise InvalidFileType(
            f"Extensión '{ext}' no permitida. "
            f"Permitidas: {', '.join(sorted(allowed_set))}"
        )


def validate_mime_type(
    mime_type: str,
    allowed_mime_prefixes: Optional[Iterable[str]] = None
) -> None:
    """
    Valida que el MIME type esté dentro de categorías permitidas.

    Args:
        mime_type: MIME type a validar (ej. 'image/png')
        allowed_mime_prefixes: Prefijos permitidos (ej. ['image/', 'application/pdf'])

    Raises:
        InvalidFileType: Si el MIME type no está permitido
    """
    if not mime_type or "/" not in mime_type:
        raise InvalidFileType(f"MIME type inválido: {mime_type}")

    if allowed_mime_prefixes:
        if not any(mime_type.startswith(prefix) for prefix in allowed_mime_prefixes):
            raise InvalidFileType(
                f"MIME type '{mime_type}' no permitido. "
                f"Permitidos: {', '.join(allowed_mime_prefixes)}"
            )


def validate_checksum_format(
    checksum: str,
    algorithm: str = "sha256"
) -> None:
    """
    Valida que el formato del checksum sea correcto para el algoritmo.

    Args:
        checksum: String del checksum a validar
        algorithm: Algoritmo usado (sha256, md5, sha1, sha512)

    Raises:
        FileValidationError: Si el formato es inválido
    """
    expected_lengths = {
        "md5": 32,
        "sha1": 40,
        "sha256": 64,
        "sha512": 128,
    }

    algo = (algorithm or "").lower()
    expected_len = expected_lengths.get(algo)
    if not expected_len:
        raise FileValidationError(f"Algoritmo de checksum no soportado: {algorithm}")

    if len(checksum) != expected_len:
        raise FileValidationError(
            f"Longitud de checksum inválida para {algorithm}: "
            f"esperado {expected_len}, recibido {len(checksum)}"
        )

    hexdigits = set("0123456789abcdefABCDEF")
    if not checksum or any(c not in hexdigits for c in checksum):
        raise FileValidationError(f"Checksum contiene caracteres inválidos: {checksum}")


__all__ = [
    "validate_file_type_consistency",
    "validate_file_size",
    "validate_filename_extension",
    "validate_mime_type",
    "validate_checksum_format",
]
# Fin del archivo backend/app/modules/files/facades/input_files/validate.py

