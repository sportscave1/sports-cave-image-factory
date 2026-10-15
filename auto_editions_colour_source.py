"""Bounded PSD ICC resource inspection and metadata-only staged assignment.

Adobe PSD resources 1039 (ICC) and 1041 (intentionally untagged) are
independent of Photoshop's machine working space. No pixels are decoded here.
"""
import hashlib
import io
from pathlib import Path
import shutil
import struct
from PIL import ImageCms

MAX_RESOURCES = 32 * 1024 * 1024
MAX_ICC = 4 * 1024 * 1024


class ColourReview(ValueError):
    """Colour evidence needs review; this does not imply a broken PSD."""


def profile_info(icc):
    if not 128 <= len(icc) <= MAX_ICC or icc[36:40] != b'acsp' or struct.unpack('>I', icc[:4])[0] != len(icc):
        raise ColourReview('Inspector failure: invalid ICC resource.')
    if icc[16:20] != b'RGB ':
        raise ColourReview('Print-colour incompatibility: RGB preparation requires an RGB profile.')
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        description = ImageCms.getProfileDescription(profile).strip()
    except (OSError, ValueError) as error:
        raise ColourReview('Inspector failure: unreadable ICC resource.') from error
    return dict(sha256=hashlib.sha256(icc).hexdigest(), description=description,
                name=ImageCms.getProfileName(profile).strip())


def _read(stream, size):
    value = stream.read(size)
    if len(value) != size:raise ColourReview('Inspector failure: truncated PSD metadata.')
    return value


def inspect_psd(path):
    """Read metadata only; malformed/unsupported inspection is never 'untagged'."""
    with Path(path).open('rb') as stream:
        header = _read(stream, 26)
        if header[:6] != b'8BPS\0\1' or header[6:12] != b'\0'*6:
            raise ColourReview('Inspector failure: unsupported PSD header.')
        channels, height, width, depth, mode = struct.unpack('>HIIHH', header[12:])
        if not 1 <= channels <= 56 or not 0 < height <= 30000 or not 0 < width <= 30000:
            raise ColourReview('Inspector failure: invalid PSD dimensions.')
        size = Path(path).stat().st_size
        colour_size = struct.unpack('>I', _read(stream, 4))[0]
        if stream.tell()+colour_size+4 > size:raise ColourReview('Inspector failure: truncated colour data.')
        stream.seek(colour_size, 1)
        length_offset = stream.tell()
        length = struct.unpack('>I', _read(stream, 4))[0]
        if length > MAX_RESOURCES or stream.tell()+length > size:
            raise ColourReview('Inspector failure: oversized or truncated PSD resources.')
        resources = _read(stream, length)
    blocks, profiles, flags = [], [], []
    pos = 0
    while pos < len(resources):
        start = pos
        if resources[pos:pos+4] != b'8BIM' or pos+7 > len(resources):
            raise ColourReview('Inspector failure: malformed PSD resources.')
        rid = struct.unpack('>H', resources[pos+4:pos+6])[0]
        name_length = resources[pos+6]+1
        pos += 6+name_length+(name_length % 2)
        if pos+4 > len(resources):raise ColourReview('Inspector failure: truncated resource name.')
        count = struct.unpack('>I', resources[pos:pos+4])[0];pos += 4
        end = pos+count
        if end+(count % 2) > len(resources):raise ColourReview('Inspector failure: truncated resource data.')
        data = resources[pos:end];pos = end+(count % 2)
        blocks.append((rid, resources[start:pos]))
        if rid == 1039:profiles.append(data)
        if rid == 1041:flags.append(data)
    if len(profiles)>1 or len(flags)>1 or any(f not in (b'\0',b'\1') for f in flags):
        raise ColourReview('Inspector failure: ambiguous ICC resources.')
    if profiles and b'\1' in flags:
        raise ColourReview('ICC export mismatch: source declares both tagged and intentionally untagged.')
    icc = profiles[0] if profiles else b''
    info = profile_info(icc) if icc else None
    return dict(state='tagged' if icc else 'untagged',icc=icc,profile=info,
                width=width,height=height,depth=depth,mode=mode,
                length_offset=length_offset,tail_offset=length_offset+4+length,blocks=blocks)


def stage_profile(source, destination, icc):
    """Assign approved interpretation by changing ICC resources only, to a new file.

    Byte-exact colour data, layers, text, fonts and composite remain untouched.
    Photoshop must subsequently reopen and agree; assignment is not certification.
    """
    source, destination = Path(source), Path(destination)
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('A new staged PSD destination is required.')
    evidence = inspect_psd(source);profile_info(icc)
    if evidence['state']!='untagged':raise ColourReview('Existing tagged artwork must retain its embedded profile.')
    if evidence['mode']!=3 or evidence['depth']!=8:
        raise ColourReview('Print-colour incompatibility: conversion requires separate approval.')
    resources = b''.join(block for rid,block in evidence['blocks'] if rid!=1041)
    resources += b'8BIM'+struct.pack('>H',1039)+b'\0\0'+struct.pack('>I',len(icc))+icc+b'\0'*(len(icc)%2)
    before = _hash(source)
    created = False
    try:
        with source.open('rb') as src, destination.open('xb') as dst:
            created = True
            dst.write(_read(src,evidence['length_offset']))
            dst.write(struct.pack('>I',len(resources)));dst.write(resources)
            src.seek(evidence['tail_offset']);shutil.copyfileobj(src,dst,4*1024*1024)
        after = inspect_psd(destination)
        if after['icc']!=icc or _hash(source)!=before or _hash(source,evidence['tail_offset'])!=_hash(destination,after['tail_offset']):
            raise ValueError('Original pixel/layer integrity check failed.')
    except Exception:
        if created:destination.unlink(missing_ok=True)
        raise
    return dict(source_sha256=before,staged_sha256=_hash(destination),
                layer_pixel_sha256=_hash(source,evidence['tail_offset']),
                icc_sha256=hashlib.sha256(icc).hexdigest(),pixels_converted=False)


def _hash(path, offset=0):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        while block:=stream.read(4*1024*1024):digest.update(block)
    return digest.hexdigest()
