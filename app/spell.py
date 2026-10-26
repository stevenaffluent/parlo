"""Is this a real word? Asks the spell checker built into Windows (ISpellChecker, Windows 8+).

Used so the personal dictionary never "corrects" ordinary words ('parlor' must not become 'Parlo').
Called through the COM vtable directly: Windows ships no type library for this interface.
"""
import ctypes
import functools
import re
import threading
from ctypes import wintypes

_ole = ctypes.OleDLL("ole32")
_ole.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
_local = threading.local()


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        s = s.strip("{}").replace("-", "")
        super().__init__(int(s[:8], 16), int(s[8:12], 16), int(s[12:16], 16),
                         (ctypes.c_ubyte * 8)(*bytes.fromhex(s[16:])))


CLSID_FACTORY = _GUID("7AB36653-1796-484B-BDFA-E74F1DB7C1DC")
IID_FACTORY = _GUID("8E018A9D-2415-4677-BF08-794EA61F94BB")


def _method(obj, index, *argtypes):
    """Function for vtable slot `index` of COM object `obj`."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtbl[index])


LANGUAGES = ("en-US", "en-GB")  # a word is real if either spelling dictionary knows it


def _checkers():
    if not hasattr(_local, "checkers"):
        _local.checkers = []
        try:
            try:
                _ole.CoInitializeEx(None, 0x2)  # apartment-threaded; harmless if already initialised
            except OSError:
                pass
            factory = ctypes.c_void_p()
            _ole.CoCreateInstance(ctypes.byref(CLSID_FACTORY), None, 1, ctypes.byref(IID_FACTORY), ctypes.byref(factory))
            for lang in LANGUAGES:
                checker = ctypes.c_void_p()
                try:
                    # ISpellCheckerFactory::CreateSpellChecker(languageTag, ISpellChecker**) is slot 5
                    _method(factory, 5, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))(factory, lang, ctypes.byref(checker))
                    _local.checkers.append(checker)
                except OSError:
                    pass  # that language's dictionary isn't installed
        except OSError:
            pass  # no spell checker at all: is_word() then says nothing is a known word
    return _local.checkers


def _known(checker, word):
    errors = ctypes.c_void_p()
    # ISpellChecker::Check(text, IEnumSpellingError**) is slot 4
    _method(checker, 4, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))(checker, word, ctypes.byref(errors))
    error = ctypes.c_void_p()
    # IEnumSpellingError::Next(ISpellingError**) is slot 3: S_OK (0) means there is a spelling error
    return _method(errors, 3, ctypes.POINTER(ctypes.c_void_p))(errors, ctypes.byref(error)) != 0


@functools.lru_cache(maxsize=4096)
def is_word(word):
    """True if Windows' English dictionary knows `word` (case-insensitive)."""
    if not word.isalpha():
        return False
    w = word.lower()
    # often only one English dictionary is installed: also accept the other spelling of the word
    variants = {w, re.sub(r"or$", "our", w), re.sub(r"our$", "or", w), re.sub(r"iz(e|ed|es|ing)$", r"is\1", w),
                re.sub(r"is(e|ed|es|ing)$", r"iz\1", w), re.sub(r"er$", "re", w), re.sub(r"re$", "er", w),
                re.sub(r"og$", "ogue", w), re.sub(r"yz(e|ed|es|ing)$", r"ys\1", w)}
    try:
        return any(_known(c, v) for c in _checkers() for v in variants)
    except OSError:
        return False
