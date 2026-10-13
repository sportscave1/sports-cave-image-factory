"""Local CLI access to the same Photoshop.Application.200 IDispatch interface.

No listener, app installation or remote command interface. Equivalent to run_inspection.ps1.
"""
import ctypes as c
import json
from pathlib import Path
import sys


class GUID(c.Structure):
    _fields_=[('a',c.c_uint32),('b',c.c_uint16),('d',c.c_uint16),('e',c.c_ubyte*8)]


class Variant(c.Structure):
    _fields_=[('vt',c.c_ushort),('r1',c.c_ushort),('r2',c.c_ushort),('r3',c.c_ushort),('value',c.c_void_p),('padding',c.c_void_p)]


class Params(c.Structure):
    _fields_=[('args',c.POINTER(Variant)),('named',c.c_void_p),('count',c.c_uint),('named_count',c.c_uint)]


class ExceptionInfo(c.Structure):
    _fields_=[('code',c.c_ushort),('reserved',c.c_ushort),('source',c.c_void_p),('description',c.c_void_p),('help',c.c_void_p),('context',c.c_uint32),('reserved_ptr',c.c_void_p),('deferred',c.c_void_p),('scode',c.c_int32)]


def run(script):
    ole=c.OleDLL('ole32');auto=c.WinDLL('oleaut32');ole.CoInitialize(None)
    auto.SysAllocString.argtypes=[c.c_wchar_p];auto.SysAllocString.restype=c.c_void_p
    auto.SysFreeString.argtypes=[c.c_void_p];auto.VariantClear.argtypes=[c.POINTER(Variant)]
    cls=GUID();iid=GUID();null=GUID();ole.CLSIDFromProgID('Photoshop.Application.200',c.byref(cls));ole.CLSIDFromString('{00020400-0000-0000-C000-000000000046}',c.byref(iid))
    dispatch=c.c_void_p();ole.CoCreateInstance(c.byref(cls),None,4,c.byref(iid),c.byref(dispatch))
    table=c.cast(dispatch,c.POINTER(c.POINTER(c.c_void_p))).contents
    getids=c.WINFUNCTYPE(c.c_int32,c.c_void_p,c.POINTER(GUID),c.POINTER(c.c_wchar_p),c.c_uint,c.c_uint,c.POINTER(c.c_int32))(table[5])
    invoke=c.WINFUNCTYPE(c.c_int32,c.c_void_p,c.c_int32,c.POINTER(GUID),c.c_uint,c.c_ushort,c.POINTER(Params),c.POINTER(Variant),c.POINTER(ExceptionInfo),c.POINTER(c.c_uint))(table[6])
    release=c.WINFUNCTYPE(c.c_uint,c.c_void_p)(table[2]);arg=Variant();out=Variant();info=ExceptionInfo()
    try:
        name=(c.c_wchar_p*1)('DoJavaScript');dispid=c.c_int32();hr=getids(dispatch,c.byref(null),name,1,0,c.byref(dispid))
        if hr<0:raise RuntimeError('Photoshop method unavailable')
        arg.vt=8;arg.value=auto.SysAllocString(script);params=Params(c.pointer(arg),None,1,0);error=c.c_uint()
        hr=invoke(dispatch,dispid,c.byref(null),0,1,c.byref(params),c.byref(out),c.byref(info),c.byref(error))
        if hr<0:raise RuntimeError('Photoshop scripting failed: '+(c.wstring_at(info.description) if info.description else hex(hr&0xffffffff)))
        return c.wstring_at(out.value) if out.vt==8 and out.value else 'Photoshop script completed'
    finally:
        auto.VariantClear(c.byref(arg));auto.VariantClear(c.byref(out))
        for ptr in (info.source,info.description,info.help):
            if ptr:auto.SysFreeString(ptr)
        release(dispatch);ole.CoUninitialize()


if __name__=='__main__':
    script=Path(sys.argv[1]);request=Path(sys.argv[2])
    if script.suffix!='.jsx' or request.suffix!='.json':raise ValueError('Expected saved local JSX and JSON')
    print(run('var SC_PSD_INSPECT_REQUEST = '+json.dumps(json.loads(request.read_text(encoding='utf-8-sig')))+';\n'+script.read_text(encoding='utf-8-sig')),flush=True)
