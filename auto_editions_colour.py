"""Restore omitted PNG ICC metadata only with per-export Photoshop evidence.

IDAT bytes and pixel values are never changed; conflicting profiles fail closed.
"""
import io
from pathlib import Path
import struct
import zlib
from PIL import Image,ImageCms


def restore_export_profiles(folder,report,names):
    folder=Path(folder)
    profiles=report.get('export_profiles',{})
    source=report.get('source_inspection',{}).get('document',{}).get('profile')
    if not source or any(profiles.get(name)!=source for name in names):
        raise ValueError('Independent Photoshop colour-profile evidence is incomplete.')
    with Image.open(folder/'original.png') as original:
        icc=original.info.get('icc_profile',b'')
    if not icc or ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip()!=source:
        raise ValueError('Original ICC profile does not match the inspected Photoshop document.')
    # Validate every export before changing even local staged metadata.
    missing=[]
    for name in names:
        path=folder/name
        if path.parent!=folder or path.is_symlink():raise ValueError('Unsafe staged PNG.')
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
                    if kind==b'IDAT':break
                    src.seek(length+4,1)
            missing.append(path)
    data=b'SportsCave ICC\0\0'+zlib.compress(icc)
    chunk=struct.pack('>I',len(data))+b'iCCP'+data+struct.pack('>I',zlib.crc32(b'iCCP'+data)&0xffffffff)
    for path in missing:
        # Stream the exact compressed pixels; no image conversion or recompression.
        temporary=path.with_suffix('.icc-tmp')
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
