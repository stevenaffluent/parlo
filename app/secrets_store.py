"""API keys encrypted with Windows DPAPI: only this Windows user on this PC can decrypt them."""
import base64
import ctypes
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt = ctypes.WinDLL("crypt32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32")
for fn in (_crypt.CryptProtectData, _crypt.CryptUnprotectData):
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(_Blob)]
    fn.restype = wintypes.BOOL
_k32.LocalFree.argtypes = [ctypes.c_void_p]
_ENTROPY = b"Parlo API key"


def _call(fn, data):
    buf = ctypes.create_string_buffer(data, len(data))
    ent = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    src, extra, out = _Blob(len(data), buf), _Blob(len(_ENTROPY), ent), _Blob()
    if not fn(ctypes.byref(src), None, ctypes.byref(extra), None, None, 0x1, ctypes.byref(out)):  # UI_FORBIDDEN
        raise OSError(ctypes.get_last_error(), "DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _k32.LocalFree(out.pbData)


def protect(text):
    return base64.b64encode(_call(_crypt.CryptProtectData, text.encode("utf-8"))).decode() if text else ""


def unprotect(blob):
    if not blob:
        return ""
    try:
        return _call(_crypt.CryptUnprotectData, base64.b64decode(blob)).decode("utf-8")
    except (OSError, ValueError):
        return ""  # e.g. settings copied from another PC: the key has to be entered again there
