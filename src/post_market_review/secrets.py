from __future__ import annotations

import os
import re
from ctypes import POINTER, Structure, byref, c_byte, c_void_p, cast, create_string_buffer, memset, string_at
from ctypes.wintypes import DWORD
from pathlib import Path


class SecretUnavailable(RuntimeError):
    pass


class _DataBlob(Structure):
    _fields_ = [("cbData", DWORD), ("pbData", POINTER(c_byte))]


def _unprotect_windows_dpapi(serialized: str) -> str:
    value = serialized.strip()
    if not value or len(value) % 2 or re.fullmatch(r"[0-9a-fA-F]+", value) is None:
        raise SecretUnavailable("SECRET_UNAVAILABLE")
    import ctypes
    encrypted = bytes.fromhex(value)
    input_buffer = create_string_buffer(encrypted, len(encrypted))
    input_blob = _DataBlob(len(encrypted), cast(input_buffer, POINTER(c_byte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(byref(input_blob), None, None, None, None, 0, byref(output_blob)):
        raise SecretUnavailable("SECRET_UNAVAILABLE")
    try:
        secret = string_at(output_blob.pbData, output_blob.cbData).decode("utf-16-le").rstrip("\x00")
        if not secret:
            raise SecretUnavailable("SECRET_UNAVAILABLE")
        return secret
    finally:
        if output_blob.pbData:
            memset(output_blob.pbData, 0, output_blob.cbData)
            kernel32.LocalFree(cast(output_blob.pbData, c_void_p))


def load_secret(env_name: str, encrypted_path: Path) -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    if os.name != "nt" or not encrypted_path.exists():
        raise SecretUnavailable("SECRET_UNAVAILABLE")
    return _unprotect_windows_dpapi(encrypted_path.read_text(encoding="utf-8-sig"))

