"""Restore omitted PNG ICC metadata only with per-export Photoshop evidence.

IDAT bytes and pixel values are never changed; conflicting profiles fail closed.
"""
from pathlib import Path
import secrets
import struct
import zlib
from PIL import Image


def restore_export_profiles(folder,report,names,*,source_icc=None):
    from auto_editions_colour_source import profile_info
    folder=Path(folder).resolve()
    # Validate every path before opening original.png or any export.
    if not names or len(names)!=len(set(names)) or 'original.png' not in names:
        raise ValueError('A unique complete export set is required.')
    for name in names:
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.png'):
            raise ValueError('Unsafe staged PNG.')
        path=folder/name
        if path.is_symlink() or path.resolve().parent!=folder:raise ValueError('Unsafe staged PNG.')
    profiles=report.get('export_profiles',{})
    source=report.get('source_inspection',{}).get('document',{}).get('profile')
    state=report.get('source_inspection',{}).get('document',{}).get('profile_state')
    if state is not None and state!='tagged':raise ValueError('Independent Photoshop colour-profile evidence is incomplete.')
    if not source or any(profiles.get(name)!=source for name in names):
        raise ValueError('Independent Photoshop colour-profile evidence is incomplete.')
    with Image.open(folder/'original.png') as original:
        original_icc=original.info.get('icc_profile',b'')
    # Source bytes are extracted independently from the staged PSD resource, not
    # from a machine working-space name. This also repairs an untagged original export.
    icc=source_icc if source_icc is not None else original_icc
    info=profile_info(icc) if icc else {}
    if not icc or source not in (info.get('description'),info.get('name')):
        raise ValueError('Original ICC profile does not match the inspected Photoshop document.')
    # Validate every export before changing even local staged metadata.
    missing=[]
    for name in names:
        path=folder/name
        with Image.open(path) as image:profile=image.info.get('icc_profile',b'')
        if profile and profile!=icc:raise ValueError('Conflicting Photoshop export colour profile.')
        if not profile:
            with path.open('rb') as src:
                src.seek(8)
                while True:
                    header=src.read(8)
                    if len(header)!=8:raise ValueError('Incomplete staged PNG.')
                    length=struct.unpack('>I',header[:4])[0];kind=header[4:]
                    if kind==b'iCCP':raise ValueError('Unverified embedded ICC profile; review required.')
                    if kind==b'IEND':break
                    if src.tell()+length+4>path.stat().st_size:raise ValueError('Incomplete staged PNG.')
                    src.seek(length+4,1)
            missing.append(path)
    data=b'SportsCave ICC\0\0'+zlib.compress(icc)
    chunk=struct.pack('>I',len(data))+b'iCCP'+data+struct.pack('>I',zlib.crc32(b'iCCP'+data)&0xffffffff)
    for path in missing:
        # Stream the exact compressed pixels; no image conversion or recompression.
        temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.icc-tmp')
        try:
            with path.open('rb') as src,temporary.open('xb') as dst:
                header=src.read(33)
                if len(header)!=33 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':
                    raise ValueError('Invalid staged PNG header.')
                dst.write(header);dst.write(chunk)
                import shutil
                shutil.copyfileobj(src,dst,4*1024*1024)
            temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
    return [path.name for path in missing]
