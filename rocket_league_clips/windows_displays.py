"""Enumerate Desktop Duplication outputs on the default DXGI adapter."""
from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class OUTPUT_DESC(ctypes.Structure):
    _fields_ = [("DeviceName", wintypes.WCHAR * 32), ("DesktopCoordinates", wintypes.RECT),
                ("AttachedToDesktop", wintypes.BOOL), ("Rotation", wintypes.UINT), ("Monitor", wintypes.HANDLE)]


class MONITOR_INFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _method(ptr, index, restype, *argtypes):
    table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])


def _release(ptr):
    if ptr and ptr.value:
        _method(ptr, 2, wintypes.ULONG)(ptr)


def displays():
    """Return names, DXGI output indices, sizes and primary flags; read-only."""
    dxgi = ctypes.WinDLL("dxgi", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    dxgi.CreateDXGIFactory1.restype = ctypes.c_long
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITOR_INFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    value = uuid.UUID("770aae78-f26f-4dba-a829-253c83d1b387")
    iid = GUID.from_buffer_copy(value.bytes_le)
    factory, adapter = ctypes.c_void_p(), ctypes.c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) < 0:
        raise RuntimeError("Could not enumerate display adapters.")
    try:
        enum_adapters = _method(factory, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        if enum_adapters(factory, 0, ctypes.byref(adapter)) < 0:
            raise RuntimeError("Could not inspect the default display adapter.")
        enum_outputs = _method(adapter, 7, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        result = []
        for index in range(64):
            output = ctypes.c_void_p()
            if enum_outputs(adapter, index, ctypes.byref(output)) < 0:
                break
            try:
                description = OUTPUT_DESC()
                if _method(output, 7, ctypes.c_long, ctypes.POINTER(OUTPUT_DESC))(output, ctypes.byref(description)) < 0:
                    continue
                if not description.AttachedToDesktop:
                    continue
                monitor = MONITOR_INFO(); monitor.cbSize = ctypes.sizeof(monitor)
                primary = bool(user32.GetMonitorInfoW(description.Monitor, ctypes.byref(monitor)) and monitor.dwFlags & 1)
                bounds = description.DesktopCoordinates
                result.append({"name": description.DeviceName, "index": index,
                               "width": bounds.right - bounds.left, "height": bounds.bottom - bounds.top,
                               "primary": primary})
            finally:
                _release(output)
        return result
    finally:
        _release(adapter); _release(factory)


def output_index(name: str | None) -> int:
    outputs = displays()
    if name is not None:
        for output in outputs:
            if output["name"] == name:
                return output["index"]
        raise RuntimeError("The selected display is unavailable. Choose a connected display in Settings.")
    return next((item["index"] for item in outputs if item["primary"]), outputs[0]["index"] if outputs else 0)
