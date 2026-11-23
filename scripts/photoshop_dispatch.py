"""Local CLI access to the installed Photoshop IDispatch interface.

No listener, app installation or remote command interface. Equivalent to run_inspection.ps1.
"""
import ctypes as c
import json
from pathlib import Path
import sys
import time
import re


def select_photoshop_registration(registrations, exists=None):
    """Prefer the newest installed version, not a stale unversioned alias.

    Resolve before activation. Never switch application versions after Invoke:
    an uncertain script result must retain its existing duplicate protection.
    """
    exists = exists or (lambda path: Path(path).is_file())
    candidates = []
    for progid, command in registrations:
        version = re.fullmatch(r'Photoshop\.Application\.(\d+)', progid, re.I)
        executable = re.match(r'^\s*"?(.+?\.exe)"?(?:\s+.*)?$', command, re.I)
        if version and executable and Path(executable[1]).name.lower() == 'photoshop.exe' and exists(executable[1]):
            candidates.append((int(version[1]), progid))
    if not candidates:
        raise PhotoshopActivationUnavailable()
    return max(candidates)[1]


def photoshop_registration():
    import winreg
    registrations = []
    index = 0
    while True:
        try:
            name = winreg.EnumKey(winreg.HKEY_CLASSES_ROOT, index)
        except OSError:
            break
        index += 1
        if not re.fullmatch(r'Photoshop\.Application\.\d+', name, re.I):
            continue
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name + r'\CLSID') as key:
                clsid = winreg.QueryValueEx(key, '')[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'CLSID\\' + clsid + r'\LocalServer32') as key:
                command = winreg.QueryValueEx(key, '')[0]
            registrations.append((name, command))
        except OSError:
            continue
    return select_photoshop_registration(registrations)


class GUID(c.Structure):
    _fields_=[('a',c.c_uint32),('b',c.c_uint16),('d',c.c_uint16),('e',c.c_ubyte*8)]


class Variant(c.Structure):
    _fields_=[('vt',c.c_ushort),('r1',c.c_ushort),('r2',c.c_ushort),('r3',c.c_ushort),('value',c.c_void_p),('padding',c.c_void_p)]


class Params(c.Structure):
    _fields_=[('args',c.POINTER(Variant)),('named',c.c_void_p),('count',c.c_uint),('named_count',c.c_uint)]


class ExceptionInfo(c.Structure):
    _fields_=[('code',c.c_ushort),('reserved',c.c_ushort),('source',c.c_void_p),('description',c.c_void_p),('help',c.c_void_p),('context',c.c_uint32),('reserved_ptr',c.c_void_p),('deferred',c.c_void_p),('scode',c.c_int32)]


class PhotoshopActivationUnavailable(RuntimeError):
    """Windows failed to start the automation server before any script ran."""

    def __init__(self):
        super().__init__('Photoshop automation server could not start (HRESULT 0x80080005)')


def activate_photoshop(create):
    # ctypes raises OSError for a failing HRESULT from OleDLL.
    for attempt in range(3):
        try:
            create()
            return
        except OSError as error:
            if getattr(error, 'winerror', None) not in (-2146959355, 0x80080005):
                raise
            if attempt == 2:
                raise PhotoshopActivationUnavailable() from error
            time.sleep(2 ** attempt)


class PhotoshopMethodUnavailable(RuntimeError):
    """The script was never invoked."""

    def __init__(self, result):
        self.busy = result in (0x80010001, 0x8001010A)
        message = 'Photoshop is busy before script dispatch' if self.busy else 'Photoshop method unavailable'
        super().__init__(f'{message} (HRESULT 0x{result:08X})')


def resolve_script_method(lookup):
    # Busy Photoshop can reject a method lookup while a tool or dialog is active.
    # Only repeat the lookup. Once Invoke begins, the script's outcome may be unknown.
    deadline = time.monotonic() + 30
    while True:
        result = lookup()
        if result >= 0:
            return
        error = PhotoshopMethodUnavailable(result & 0xffffffff)
        if not error.busy or time.monotonic() >= deadline:
            raise error
        time.sleep(1)


def run(script):
    ole=c.OleDLL('ole32');auto=c.WinDLL('oleaut32');ole.CoInitialize(None)
    try:
        return _run(ole, auto, script)
    finally:
        ole.CoUninitialize()

def restore_photoshop_window(user=None):
    """ExtendScript bringToFront does not reliably undo native minimization."""
    user=user or c.WinDLL('user32')
    user.GetClassNameW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_int]
    user.IsWindowVisible.argtypes=[c.c_void_p]
    user.IsIconic.argtypes=[c.c_void_p]
    user.ShowWindow.argtypes=[c.c_void_p,c.c_int]
    callback=c.WINFUNCTYPE(c.c_bool,c.c_void_p,c.c_void_p)
    restored=[]
    def visit(window,_):
        name=c.create_unicode_buffer(256)
        user.GetClassNameW(window,name,len(name))
        if name.value=='Photoshop' and user.IsWindowVisible(window) and user.IsIconic(window):
            user.ShowWindow(window,9) # SW_RESTORE; preserve open documents.
            restored.append(window)
        return True
    user.EnumWindows(callback(visit),0)
    return len(restored)


def _run(ole, auto, script):
    auto.SysAllocString.argtypes=[c.c_wchar_p];auto.SysAllocString.restype=c.c_void_p
    auto.SysFreeString.argtypes=[c.c_void_p];auto.VariantClear.argtypes=[c.POINTER(Variant)]
    cls=GUID();iid=GUID();null=GUID();ole.CLSIDFromProgID(photoshop_registration(),c.byref(cls));ole.CLSIDFromString('{00020400-0000-0000-C000-000000000046}',c.byref(iid))
    dispatch=c.c_void_p()
    activate_photoshop(lambda: ole.CoCreateInstance(c.byref(cls),None,4,c.byref(iid),c.byref(dispatch)))
    restore_photoshop_window()
    table=c.cast(dispatch,c.POINTER(c.POINTER(c.c_void_p))).contents
    getids=c.WINFUNCTYPE(c.c_int32,c.c_void_p,c.POINTER(GUID),c.POINTER(c.c_wchar_p),c.c_uint,c.c_uint,c.POINTER(c.c_int32))(table[5])
    invoke=c.WINFUNCTYPE(c.c_int32,c.c_void_p,c.c_int32,c.POINTER(GUID),c.c_uint,c.c_ushort,c.POINTER(Params),c.POINTER(Variant),c.POINTER(ExceptionInfo),c.POINTER(c.c_uint))(table[6])
    release=c.WINFUNCTYPE(c.c_uint,c.c_void_p)(table[2]);arg=Variant();out=Variant();info=ExceptionInfo()
    try:
        name=(c.c_wchar_p*1)('DoJavaScript');dispid=c.c_int32()
        resolve_script_method(lambda: getids(dispatch,c.byref(null),name,1,0,c.byref(dispid)))
        arg.vt=8;arg.value=auto.SysAllocString(script);params=Params(c.pointer(arg),None,1,0);error=c.c_uint()
        hr=invoke(dispatch,dispid,c.byref(null),0,1,c.byref(params),c.byref(out),c.byref(info),c.byref(error))
        if hr<0:raise RuntimeError('Photoshop scripting failed: '+(c.wstring_at(info.description) if info.description else hex(hr&0xffffffff)))
        return c.wstring_at(out.value) if out.vt==8 and out.value else 'Photoshop script completed'
    finally:
        auto.VariantClear(c.byref(arg));auto.VariantClear(c.byref(out))
        for ptr in (info.source,info.description,info.help):
            if ptr:auto.SysFreeString(ptr)
        release(dispatch)


if __name__=='__main__':
    script=Path(sys.argv[1]);request=Path(sys.argv[2])
    if script.suffix!='.jsx' or request.suffix!='.json':raise ValueError('Expected saved local JSX and JSON')
    print(run('var SC_PSD_INSPECT_REQUEST = '+json.dumps(json.loads(request.read_text(encoding='utf-8-sig')))+';\n'+script.read_text(encoding='utf-8-sig')),flush=True)
