"""Optional byte-exact compaction of a verified legacy packet into a new job folder."""
import json
from pathlib import Path
import tempfile
import time
import zipfile
import auto_editions as ae
from auto_editions_package import unpack
from auto_editions_transport import build_package, DESCRIPTOR, MAX_DELTA


def shared(left,right,left_size,right_size):
    size=min(left_size,right_size);prefix=suffix=0;block=1024*1024
    while prefix<size:
        n=min(block,size-prefix);a=left.read(n);b=right.read(n)
        if a==b:prefix+=n;continue
        prefix+=next(i for i in range(n) if a[i]!=b[i]);break
    while suffix<size-prefix:
        n=min(block,size-prefix-suffix)
        left.seek(left_size-suffix-n);right.seek(right_size-suffix-n)
        a=left.read(n);b=right.read(n)
        if a==b:suffix+=n;continue
        suffix+=next(i for i in range(n) if a[-1-i]!=b[-1-i]);break
    return prefix,suffix


def verify_provenance(source,generation):
    source=Path(source);identity=source.parent/'package-identity.json'
    if not identity.is_file() or identity.is_symlink() or identity.stat().st_size>4096:
        raise ValueError('Retained resumable packet requires original generation evidence.')
    record=json.loads(identity.read_text(encoding='utf-8'))
    if record.get('generation')!=generation or record.get('sha256')!=ae.file_hash(source):
        raise ValueError('Retained package generation or checksum changed.')
    return record


def compact_retained(source,destination,context,generation,max_bytes,*,min_savings=8*1024*1024):
    source=Path(source);destination=Path(destination)
    started=time.monotonic()
    def unchanged(reason):return source,dict(repack_outcome=reason,repack_seconds=round(time.monotonic()-started,6))
    if source.resolve()==destination.resolve() or destination.exists():return unchanged('existing packet preserved')
    if source.is_symlink() or source.parent.is_symlink() or destination.parent.is_symlink():raise ValueError('Linked repack path refused.')
    if any((p/'upload-session.json').exists() for p in (source.parent,destination.parent)):
        return unchanged('durable session descriptor preserved')
    identity=source.parent/'package-identity.json'
    if not identity.is_file() or identity.is_symlink() or identity.stat().st_size>4096:return unchanged('missing provenance')
    record=verify_provenance(source,generation)
    from auto_editions_package_limits import EXPANDED_BYTES,ASSET_BYTES,RESUMABLE_BYTES
    if source.stat().st_size>max_bytes:return unchanged('package exceeds negotiated budget')
    with zipfile.ZipFile(source) as packet:
        entries=packet.infolist();names=[i.filename for i in entries]
        if DESCRIPTOR in names:return unchanged('already compact')
        if len(names)!=len(set(names)) or len(names)>1010 or sum(i.file_size for i in entries)>EXPANDED_BYTES:
            raise ValueError('Retained package inventory changed.')
        if any(Path(n).name!=n or '\\' in n or packet.getinfo(n).file_size>ASSET_BYTES for n in names):raise ValueError('Unsafe retained member.')
        if packet.getinfo('manifest.json').file_size>1024*1024:raise ValueError('Bounded retained manifest required.')
        manifest=json.loads(packet.read('manifest.json'))
        if ae.fingerprint(manifest)!=record.get('preparation_hash'):raise ValueError('Retained manifest identity changed.')
        if manifest['source']!=context['source'] or manifest['edition_total']!=context['total']:
            raise ValueError('Retained preparation context changed.')
        if context.get('reset_id') and manifest.get('reset_request_id')!=context['reset_id']:raise ValueError('Reset requires a fresh packet.')
        saving=0;base=packet.getinfo('original.png')
        import re
        for name in names:
            if not re.fullmatch(r'reference-[1-9][0-9]*\.png',name):continue
            target=packet.getinfo(name)
            with packet.open(base) as left,packet.open(target) as right:
                prefix,suffix=shared(left,right,base.file_size,target.file_size)
            if target.file_size-prefix-suffix<=MAX_DELTA and prefix+suffix>=65536:saving+=prefix+suffix
    if saving<max(min_savings,source.stat().st_size*.05):return unchanged('insufficient byte sharing')
    parent=destination.parent.resolve()
    # Every temporary cleanup stays inside the exact newly owned destination folder.
    with tempfile.TemporaryDirectory(prefix='repack-',dir=parent) as temporary:
        root=Path(temporary).resolve();assert root.parent==parent
        old=root/'old';new=root/'new';old.mkdir();new.mkdir()
        validated,proofs=unpack(source,old,context['source'],context['number'],context['total'],resumable=max_bytes==RESUMABLE_BYTES)
        from auto_editions_preparation_geometry import matches
        if not matches(validated,context):raise ValueError('Retained preparation geometry changed.')
        created=False
        try:
            info=build_package(old,sorted(p.name for p in old.iterdir()),destination,compact=True,max_bytes=max_bytes)
            created=True
            rebuilt,_=unpack(destination,new,context['source'],context['number'],context['total'],resumable=max_bytes==RESUMABLE_BYTES)
            if rebuilt!=validated or any(not (new/p.name).is_file() or ae.file_hash(p)!=ae.file_hash(new/p.name) for p in old.iterdir()):
                raise ValueError('Repacked assets differ from verified originals.')
            if source.stat().st_size-destination.stat().st_size<min_savings:
                destination.unlink();return unchanged('no worthwhile final saving')
            from companion_atomic import atomic_json
            atomic_json(parent/'package-identity.json',dict(generation=generation,preparation_hash=ae.fingerprint(validated),sha256=ae.file_hash(destination)))
        except Exception:
            if created:destination.unlink(missing_ok=True)
            raise
    return destination,dict(repack_outcome='verified compact packet',repack_seconds=round(time.monotonic()-started,6),
                            repack_saved_bytes=source.stat().st_size-destination.stat().st_size,**info)
