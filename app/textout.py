"""Putting text into the focused app: clipboard paste (with restore) or simulated typing."""
import ctypes
import time
from ctypes import wintypes

from pynput.keyboard import Controller, Key

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32.OpenClipboard.argtypes = [wintypes.HWND]
u32.OpenClipboard.restype = wintypes.BOOL
u32.GetClipboardData.argtypes = [wintypes.UINT]
u32.GetClipboardData.restype = wintypes.HANDLE
u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
u32.SetClipboardData.restype = wintypes.HANDLE
u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
u32.RegisterClipboardFormatW.restype = wintypes.UINT
u32.GetClipboardSequenceNumber.restype = wintypes.DWORD
k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wintypes.HGLOBAL
k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
k32.GlobalLock.restype = wintypes.LPVOID
k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 2
# Formats that ask Windows clipboard history, cloud clipboard and clipboard managers to skip our temporary text
_PRIVATE = ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")

kb = Controller()


def _open():
    for _ in range(25):
        if u32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _alloc(data):
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    return h


def get_clipboard_text():
    if not _open():
        return None
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def set_clipboard_text(text, private=False):
    if not _open():
        return False
    try:
        u32.EmptyClipboard()
        u32.SetClipboardData(CF_UNICODETEXT, _alloc((text + "\0").encode("utf-16-le")))
        if private:
            for name in _PRIVATE:
                u32.SetClipboardData(u32.RegisterClipboardFormatW(name), _alloc(b"\0\0\0\0"))
        return True
    finally:
        u32.CloseClipboard()


def clipboard_seq():
    return u32.GetClipboardSequenceNumber()


def _chord(mod, key):
    kb.press(mod)
    kb.press(key)
    kb.release(key)
    kb.release(mod)


def paste_text(text, restore=True):
    """Put text on the clipboard, press Ctrl+V, then give the user back their previous clipboard text."""
    old = get_clipboard_text() if restore else None
    if not set_clipboard_text(text, private=True):
        type_text(text)
        return
    time.sleep(0.03)
    _chord(Key.ctrl, "v")
    if old is not None:
        time.sleep(0.4)  # the target app reads the clipboard asynchronously
        set_clipboard_text(old)


def type_text(text):
    kb.type(text)


def press_enter():
    time.sleep(0.05)
    kb.tap(Key.enter)


def copy_selection(timeout=0.6):
    """Ctrl+C the current selection and return it ('' if nothing was selected); the clipboard is restored."""
    old = get_clipboard_text()
    before = clipboard_seq()
    _chord(Key.ctrl, "c")
    end = time.time() + timeout
    while clipboard_seq() == before and time.time() < end:
        time.sleep(0.02)
    if clipboard_seq() == before:
        return ""
    time.sleep(0.03)
    text = get_clipboard_text() or ""
    if old is not None:
        set_clipboard_text(old)
    return text


# ---- keyboard actions and the app in front ----------------------------------------------
_KEYS = {"enter": Key.enter, "tab": Key.tab, "escape": Key.esc, "backspace": Key.backspace}


def run_action(action, last_inserted=""):
    """Voice actions: undo, delete the last dictation, select all, copy, or press a key."""
    if action == "undo":
        _chord(Key.ctrl, "z")
    elif action == "select_all":
        _chord(Key.ctrl, "a")
    elif action == "copy":
        _chord(Key.ctrl, "c")
    elif action == "delete_last":
        for _ in range(len(last_inserted)):
            kb.tap(Key.backspace)
    elif action in _KEYS:
        time.sleep(0.05)
        kb.tap(_KEYS[action])


def foreground_app():
    """(exe name, window title) of the app in front, e.g. ('outlook.exe', 'Inbox - Outlook')."""
    u32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    title = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(hwnd, title, 256)
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    exe = ""
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            exe = buf.value.rsplit("\\", 1)[-1].lower()
        k32.CloseHandle(h)
    return exe, title.value
