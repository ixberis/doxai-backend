
# tests/modules/files/services/input_files/test_file_checksum_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio de checksums de archivos del módulo Files.

Cubre:
- Cálculo de hash en múltiples algoritmos soportados
- Verificación de formato hex y longitud esperada por algoritmo
- Cálculo a partir de bytes y a partir de streams (file-like)
- Comparación contra hashlib (fuente de verdad)
- Validación/Verificación de checksum correcto e incorrecto
- Manejo de algoritmos no soportados
"""

import io
import os
import binascii
import hashlib
import pytest

from app.modules.files.enums.checksum_algo_enum import ChecksumAlgo
from app.modules.files.services.file_checksum_service import (
    compute_checksum,          # (data: bytes | IO[bytes], algo: ChecksumAlgo | str) -> str
    compute_checksum_stream,   # (stream: IO[bytes], algo: ChecksumAlgo | str, chunk_size: int=...) -> str
    verify_checksum,           # (data: bytes | IO[bytes], expected_hex: str, algo: ChecksumAlgo | str) -> bool
)


@pytest.mark.parametrize(
    "algo,expected_len",
    [
        (ChecksumAlgo.md5, 32),
        (ChecksumAlgo.sha1, 40),
        (ChecksumAlgo.sha256, 64),
        (ChecksumAlgo.sha512, 128),
    ],
)
def test_compute_checksum_from_bytes_matches_hashlib_and_hex_len(algo, expected_len):
    """Verifica que compute_checksum genere el mismo valor que hashlib y con longitud correcta."""
    payloads = [
        b"",
        b"hola",
        b"DoxAI Files - checksum end-to-end",
        os.urandom(256),
    ]

    for data in payloads:
        h = compute_checksum(data, algo)
        assert isinstance(h, str)
        assert len(h) == expected_len
        try:
            binascii.unhexlify(h)
        except binascii.Error as e:
            pytest.fail(f"Checksum no es hex válido: {h!r} ({e})")

        ref = hashlib.new(str(algo.value).lower(), data).hexdigest()
        assert h == ref


@pytest.mark.parametrize(
    "algo,expected_len",
    [
        (ChecksumAlgo.md5, 32),
        (ChecksumAlgo.sha1, 40),
        (ChecksumAlgo.sha256, 64),
        (ChecksumAlgo.sha512, 128),
    ],
)
def test_compute_checksum_from_stream_chunked(algo, expected_len, tmp_path):
    """Verifica que compute_checksum_stream funcione correctamente en modo chunked."""
    chunk = b"DoxAI-" * 10_000
    file_path = tmp_path / "big.bin"
    with open(file_path, "wb") as f:
        for _ in range(128):
            f.write(chunk)

    with open(file_path, "rb") as stream:
        h_stream = compute_checksum_stream(stream, algo, chunk_size=64 * 1024)

    assert isinstance(h_stream, str)
    assert len(h_stream) == expected_len
    binascii.unhexlify(h_stream)

    with open(file_path, "rb") as stream:
        ref = hashlib.new(str(algo.value).lower())
        for b in iter(lambda: stream.read(64 * 1024), b""):
            ref.update(b)
    assert h_stream == ref.hexdigest()


@pytest.mark.parametrize("algo", [ChecksumAlgo.md5, ChecksumAlgo.sha1, ChecksumAlgo.sha256, ChecksumAlgo.sha512])
def test_verify_checksum_true_with_bytes(algo):
    """Debe retornar True si el checksum coincide al calcular desde bytes."""
    data = b"verificacion-checksum"
    expected = hashlib.new(str(algo.value).lower(), data).hexdigest()
    assert verify_checksum(data, expected_hex=expected, algo=algo) is True


@pytest.mark.parametrize("algo", [ChecksumAlgo.md5, ChecksumAlgo.sha1, ChecksumAlgo.sha256, ChecksumAlgo.sha512])
def test_verify_checksum_true_with_stream(algo):
    """Debe retornar True si el checksum coincide al calcular desde un stream."""
    data = b"DoxAI-stream-verification"
    stream = io.BytesIO(data)
    expected = hashlib.new(str(algo.value).lower(), data).hexdigest()
    assert verify_checksum(stream, expected_hex=expected, algo=algo) is True


@pytest.mark.parametrize("algo", [ChecksumAlgo.md5, ChecksumAlgo.sha1, ChecksumAlgo.sha256, ChecksumAlgo.sha512])
def test_verify_checksum_false_when_mismatch(algo):
    """Debe retornar False si el checksum esperado no coincide."""
    data = b"contenido-original"
    wrong = hashlib.new(str(algo.value).lower(), b"OTRO").hexdigest()
    assert verify_checksum(data, expected_hex=wrong, algo=algo) is False


def test_unsupported_algorithm_raises_meaningful_error():
    """Debe lanzar un error claro si el algoritmo no es soportado."""
    data = b"payload"
    with pytest.raises((ValueError, KeyError, NotImplementedError)) as exc:
        compute_checksum(data, "sha3_999")
    assert "sha3_999" in str(exc.value).lower()


def test_hex_validation_case_insensitive():
    """El checksum debe validarse de forma case-insensitive (mayúsculas/minúsculas)."""
    data = b"Case-Insensitive-Hex"
    h = compute_checksum(data, ChecksumAlgo.sha256)
    assert verify_checksum(data, expected_hex=h.upper(), algo=ChecksumAlgo.sha256) is True


# Fin del archivo tests/modules/files/services/input_files/test_file_checksum_service.py
