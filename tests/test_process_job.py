import ctypes
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects only")
def test_recorder_child_is_terminated_if_parent_dies():
    script = """
import os, subprocess, sys
from rocket_league_clips.process_job import KillOnCloseJob
job = KillOnCloseJob()
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=subprocess.CREATE_NO_WINDOW)
job.assign(child)
print(child.pid, flush=True)
os._exit(0)
"""
    parent = subprocess.run([sys.executable, "-u", "-c", script], capture_output=True, text=True, timeout=10, check=True)
    pid = int(parent.stdout.strip())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 3000) == 0
        finally:
            kernel.CloseHandle(handle)
