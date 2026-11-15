"""Lossless ZIP transport: retain every reference byte, share unchanged spans.

This changes neither the preparation manifest nor any image. Full server ICC,
asset hashes and independent pixel proofs still run after exact reconstruction.
Only use compact packets when the scoped server advertises transport version 1.
"""
import hashlib,json,re,shutil,zipfile
from pathlib import Path

VERSION=1
DESCRIPTOR='transport.json'
MAX_DELTA=1024*1024
BLOCK=1024*1024

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def spans(base,target):
    """Find exact shared prefix/suffix with bounded buffers, never decode pixels."""
    size=min(base.stat().st_size,target.stat().st_size);prefix=0;suffix=0
    with base.open('rb') as left,target.open('rb') as right:
        while prefix<size:
            n=min(BLOCK,size-prefix);a=left.read(n);b=right.read(n)
            if a==b:prefix+=n;continue
            prefix+=next(i for i in range(n) if a[i]!=b[i]);break
        while suffix<size-prefix:
            n=min(BLOCK,size-prefix-suffix)
            left.seek(base.stat().st_size-suffix-n);right.seek(target.stat().st_size-suffix-n)
            a=left.read(n);b=right.read(n)
            if a==b:suffix+=n;continue
            suffix+=next(i for i in range(n) if a[-1-i]!=b[-1-i]);break
    return prefix,suffix

def build_package(root,names,destination,*,compact=False,max_bytes=None):
    root=Path(root).resolve();destination=Path(destination)
    from auto_editions_package import MAX_PACKAGE_BYTES
    from auto_editions_package_limits import RESUMABLE_BYTES,EXPANDED_BYTES,ASSET_BYTES,DISK_RESERVE,transfer_error,PackageBudgetError
    if max_bytes is None:max_bytes=MAX_PACKAGE_BYTES
    if type(max_bytes) is not int or max_bytes not in (MAX_PACKAGE_BYTES,RESUMABLE_BYTES):raise ValueError('Unnegotiated package budget.')
    if len(names)!=len(set(names)):raise ValueError('Unique package members required.')
    if len(names)>1009:raise ValueError('Too many generated package members.')
    for n in names:
        if Path(n).name!=n or (root/n).is_symlink() or (root/n).resolve().parent!=root:
            raise ValueError('Unsafe prepared package member.')
    expanded=sum((root/n).stat().st_size for n in names)
    if expanded>EXPANDED_BYTES:raise PackageBudgetError(f'Expanded preparation is {expanded} bytes; supported disk limit is {EXPANDED_BYTES} bytes.')
    if any((root/n).stat().st_size>(1024*1024 if n=='manifest.json' else ASSET_BYTES) for n in names):
        raise PackageBudgetError('Generated asset exceeds its supported individual byte limit; retain the source for review.')
    deltas={};payloads={};saved=0
    base=root/'original.png'
    if compact and 'original.png' in names:
        base_hash=None
        for name in names:
            if not re.fullmatch(r'reference-[1-9][0-9]*\.png',name):continue
            target=root/name;prefix,suffix=spans(base,target)
            middle=target.stat().st_size-prefix-suffix
            # Do not spend CPU or enlarge a packet for dissimilar images.
            if middle>MAX_DELTA or prefix+suffix<64*1024:continue
            if base_hash is None:base_hash=digest(base)
            payload='transport-'+name[:-4]+'.bin'
            with target.open('rb') as stream:stream.seek(prefix);payloads[payload]=stream.read(middle)
            deltas[name]=dict(base='original.png',base_sha256=base_hash,prefix=prefix,suffix=suffix,
                              bytes=target.stat().st_size,sha256=digest(target),delta=payload,
                              delta_sha256=hashlib.sha256(payloads[payload]).hexdigest())
            saved+=prefix+suffix
    temporary=destination.with_name(destination.name+'.partial')
    if destination.exists() or temporary.exists():raise ValueError('Existing transport evidence is never overwritten.')
    descriptor_bytes=json.dumps(dict(version=VERSION,deltas=deltas),sort_keys=True).encode() if deltas else None
    members={n:(root/n).stat().st_size for n in names if n not in deltas}
    if deltas:members.update({DESCRIPTOR:len(descriptor_bytes)},**{n:len(v) for n,v in payloads.items()})
    if sum(members.values())+sum(d['bytes'] for d in deltas.values())>EXPANDED_BYTES:
        raise PackageBudgetError('Expanded preparation plus transport evidence exceeds the supported disk budget.')
    # ZIP_STORED, flat UTF-8 names, no ZIP64 members: exact wire size before
    # writing another large copy or starting any expensive network request.
    predicted=22+sum(size+76+2*len(name.encode('utf-8')) for name,size in members.items())
    if predicted>max_bytes:raise transfer_error(predicted,max_bytes)
    if shutil.disk_usage(destination.parent).free<predicted+DISK_RESERVE:
        raise PackageBudgetError(f'Preparation needs {predicted+DISK_RESERVE} free temporary bytes before packaging; exports retained for retry.')
    try:
        with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_STORED) as z:
            for name in names:
                if name not in deltas:z.write(root/name,name)
            if deltas:
                z.writestr(DESCRIPTOR,descriptor_bytes)
                for name,data in payloads.items():z.writestr(name,data)
        if temporary.stat().st_size>max_bytes:raise transfer_error(temporary.stat().st_size,max_bytes)
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return dict(transport_version=VERSION if deltas else 0,references_shared=len(deltas),
                shared_bytes=saved,package_bytes=destination.stat().st_size,expanded_bytes=expanded,transfer_limit_bytes=max_bytes)

def descriptor(package,allowed):
    """Validate the expanded logical file set before extracting any member."""
    names=set(package.namelist());extra={};deltas={}
    if DESCRIPTOR in names:
        if package.getinfo(DESCRIPTOR).file_size>16384:raise ValueError('Transport descriptor exceeds bounds.')
        data=json.loads(package.read(DESCRIPTOR))
        if not isinstance(data,dict) or set(data)!={'version','deltas'} or type(data['version']) is not int or data['version']!=VERSION:
            raise ValueError('Unsupported package transport.')
        deltas=data['deltas']
        if not isinstance(deltas,dict) or not 1<=len(deltas)<=3:raise ValueError('Bounded reference deltas required.')
        extra={DESCRIPTOR}
        for target,d in deltas.items():
            if target not in allowed or not re.fullmatch(r'reference-[1-9][0-9]*\.png',target) or target in names:
                raise ValueError('Invalid shared reference.')
            if not isinstance(d,dict) or set(d)!={'base','base_sha256','prefix','suffix','bytes','sha256','delta','delta_sha256'}:
                raise ValueError('Invalid reference delta evidence.')
            if d['base']!='original.png' or d['base'] not in names or d['delta']!='transport-'+target[:-4]+'.bin':
                raise ValueError('Unsafe reference delta dependency.')
            if any(type(d[k]) is not int or d[k]<0 for k in ('prefix','suffix','bytes')):
                raise ValueError('Invalid reference delta range.')
            if any(not re.fullmatch(r'[a-f0-9]{64}',str(d[k])) for k in ('sha256','base_sha256','delta_sha256')):
                raise ValueError('Reference hashes required.')
            if d['delta'] not in names:raise ValueError('Missing reference delta.')
            length=package.getinfo(d['delta']).file_size;base_size=package.getinfo(d['base']).file_size
            if length>MAX_DELTA or d['bytes']>160*1024*1024 or d['prefix']+d['suffix']>base_size or d['prefix']+d['suffix']+length!=d['bytes']:
                raise ValueError('Reference delta exceeds bounds.')
            extra.add(d['delta'])
    if names!=(allowed-set(deltas))|set(extra):raise ValueError('Only exact generated assets and transport evidence are allowed.')
    return deltas

def reconstruct(root,deltas):
    root=Path(root)
    def copy_n(src,dst,n):
        while n:
            block=src.read(min(BLOCK,n))
            if not block:raise ValueError('Truncated reference delta.')
            dst.write(block);n-=len(block)
    for target,d in deltas.items():
        base=root/d['base'];delta=root/d['delta'];output=root/target
        if digest(base)!=d['base_sha256'] or digest(delta)!=d['delta_sha256']:
            raise ValueError('Reference delta bytes changed.')
        with base.open('rb') as src,output.open('xb') as dst:
            copy_n(src,dst,d['prefix'])
            with delta.open('rb') as patch:shutil.copyfileobj(patch,dst,BLOCK)
            src.seek(base.stat().st_size-d['suffix']);copy_n(src,dst,d['suffix'])
        if output.stat().st_size!=d['bytes'] or digest(output)!=d['sha256']:
            raise ValueError('Reconstructed reference differs from its independent export.')
