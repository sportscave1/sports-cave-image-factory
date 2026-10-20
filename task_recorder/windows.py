"""Recorder-only Windows facilities. No editions/Photoshop imports or controls."""
import ctypes
import json
import os
from pathlib import Path
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Device credentials require Windows DPAPI.")
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        kernel.LocalFree(out.data)


class Vault:
    def __init__(self, root):
        self.path = Path(root) / "local-private.json"

    def read(self):
        if not self.path.exists(): return {}
        return json.loads(protect(bytes.fromhex(self.path.read_text()), True))

    def write(self, value):
        from .store import atomic
        # Store the opaque DPAPI blob; never plaintext file paths/device keys.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(protect(json.dumps(value).encode()).hex())
        os.replace(tmp, self.path)

    def put(self, key, value):
        data = self.read()
        data[key] = value
        self.write(data)

    def file(self, ref):
        return self.read().get("files", {}).get(ref, "")

    def add_file(self, path):
        import uuid
        from .schema import PRIVATE
        path = Path(path).resolve()
        if not path.is_file() or PRIVATE.search(path.name):
            raise ValueError("Choose an ordinary task file, not a credentials file.")
        data = self.read()
        ref = str(uuid.uuid4())
        data.setdefault("files", {})[ref] = str(path)
        self.write(data)
        return ref


def choose_file():
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(parent=window, title="Task Recorder — choose a file to reuse")
    finally:
        window.destroy()


def startup(enabled):
    import winreg
    launcher = Path(os.environ["LOCALAPPDATA"]) / "SportsCaveOS" / "TaskRecorderHelper" / "Start.vbs"
    if enabled and not launcher.is_file():
        raise ValueError("Install the helper first using Setup.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "SportsCaveTaskRecorder", 0, winreg.REG_SZ, 'wscript.exe "' + str(launcher) + '"')
        else:
            try: winreg.DeleteValue(key, "SportsCaveTaskRecorder")
            except FileNotFoundError: pass
