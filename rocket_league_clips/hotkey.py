"""Windows RegisterHotKey on a dedicated message-loop thread."""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
VK_F8 = 0x77


class HotkeyError(RuntimeError):
    pass


class GlobalHotkey:
    def __init__(self, callback, key=VK_F8, modifiers=0, debounce=0.2):
        self.callback = callback
        self.key = key
        self.modifiers = modifiers
        self.debounce = debounce
        self._ready = threading.Event()
        self._thread = None
        self._thread_id = None
        self._error = None

    def start(self):
        if self._thread:
            raise HotkeyError("Shortcut listener is already started.")
        self._thread = threading.Thread(target=self._run, name="global-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            raise HotkeyError("Windows did not initialize the shortcut listener.")
        if self._error:
            raise HotkeyError(self._error)

    def _run(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._thread_id = kernel32.GetCurrentThreadId()
        # PeekMessage creates this thread's queue before it can be stopped.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        if not user32.RegisterHotKey(None, 1, self.modifiers | MOD_NOREPEAT, self.key):
            error = ctypes.get_last_error()
            self._error = f"The shortcut could not be registered (Windows error {error}); it may already be in use."
            self._ready.set()
            return
        self._ready.set()
        last = 0.0
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == 1:
                    now = time.monotonic()
                    if now - last >= self.debounce:
                        last = now
                        try:
                            # The callback must only enqueue or emit a signal.
                            self.callback()
                        except Exception:
                            pass
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self._thread_id and self._thread and self._thread.is_alive():
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=5)
