"""Wake the existing app when its executable is started again on Windows."""
import ctypes
import time

EVENT_NAME = r"Local\RocketLeagueClipsOpenWindow"
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateEventW.restype = ctypes.c_void_p
    kernel.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.OpenEventW.restype = ctypes.c_void_p
    kernel.SetEvent.argtypes = [ctypes.c_void_p]
    kernel.SetEvent.restype = ctypes.c_bool
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_bool
    return kernel


class ActivationEvent:
    def __init__(self, name=EVENT_NAME):
        self.kernel = _kernel()
        # Auto-reset coalesces repeated shortcut launches into one request.
        self.handle = self.kernel.CreateEventW(None, False, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def requested(self):
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def signal_existing(name=EVENT_NAME, timeout=5.0):
    """Allow time for the first process to create its event during startup."""
    kernel = _kernel()
    deadline = time.monotonic() + timeout
    while True:
        handle = kernel.OpenEventW(EVENT_MODIFY_STATE, False, name)
        if handle:
            try:
                if not kernel.SetEvent(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                return True
            finally:
                kernel.CloseHandle(handle)
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
