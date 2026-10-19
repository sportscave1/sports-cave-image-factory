"""Validate a bounded, generated-assets-only preparation archive before storage."""
import json
from pathlib import Path
import zipfile
import auto_editions as ae

MAX_PACKAGE_BYTES=256*1024*1024


def unpack(archive,root,source,number,total):
    root=Path(root)
    with zipfile.ZipFile(archive) as package:
        entries=package.infolist()
        names=[e.filename for e in entries]
        if len(names)!=len(set(names)) or len(names)>1010 or sum(e.file_size for e in entries)>MAX_PACKAGE_BYTES:
            raise ValueError('Preparation package exceeds its bounds or has duplicate entries.')
        if any('/' in n or '\\' in n or n in ('.','..') for n in names):
            raise ValueError('Preparation package must contain flat generated files only.')
        if 'manifest.json' not in names or package.getinfo('manifest.json').file_size>1024*1024:
            raise ValueError('A bounded preparation manifest is required.')
        manifest=ae.validate_manifest(json.loads(package.read('manifest.json')))
        if manifest['source']!=source or manifest['edition_total']!=total:
            raise ValueError('Prepared source or edition total differs from the current linked allocation.')
        if manifest['dimensions'][0]*manifest['dimensions'][1]>ae.WORKER_MAX_PIXELS:
            raise ValueError('This layout needs a separately verified production worker budget.')
        refs=sorted({1,number,total})
        allowed={'manifest.json','original.png'}|{f'reference-{n}.png' for n in refs}
        allowed|={manifest['master']['name']}|{p['name'] for p in manifest['patches'].values()}
        from auto_editions_role_evidence import resolution
        reviewed=resolution(source)
        if reviewed and reviewed.get('hidden_number'):allowed.add('uncorrected.png')
        from auto_editions_transport import descriptor,reconstruct
        deltas=descriptor(package,allowed)
        if sum(e.file_size for e in entries)+sum(d['bytes'] for d in deltas.values())>MAX_PACKAGE_BYTES:
            raise ValueError('Expanded preparation package exceeds its bounds.')
        for entry in entries:
            # No ZipFile.extract; symbolic links/directories cannot change destinations.
            if entry.is_dir() or entry.file_size>160*1024*1024:raise ValueError('Invalid generated asset.')
            with package.open(entry) as content,(root/entry.filename).open('xb') as output:
                length=0
                while block:=content.read(1024*1024):
                    length+=len(block)
                    if length>entry.file_size:raise ValueError('Generated asset length changed.')
                    output.write(block)
                if length!=entry.file_size:raise ValueError('Generated asset is truncated.')
    reconstruct(root,deltas)
    # Checksums for every numbered patch, not just the sample reference.
    for asset in [manifest['master']]+list(manifest['patches'].values()):ae.asset_path(root,asset)
    colour=manifest.get('colour_evidence')
    if colour:
        from auto_editions_colour_source import profile_info
        from PIL import Image
        expected=colour.get('icc_sha256')
        if colour.get('pixels_converted') is not False:raise ValueError('Unapproved colour conversion.')
        if colour.get('policy'):
            from auto_editions_colour_policy import resolve
            _,approved=resolve(source)
            if colour['policy']!=approved or expected!=approved['icc_sha256']:
                raise ValueError('Colour policy awaiting approval: package policy changed.')
        for name in allowed-{'manifest.json'}:
            with Image.open(root/name) as image:
                if profile_info(image.info.get('icc_profile',b''))['sha256']!=expected:
                    raise ValueError('ICC export mismatch: package profile evidence differs.')
    from auto_editions_artwork_recovery import verify_package
    verify_package(root,manifest)
    proofs=[ae.compare_reference(manifest,root,n,root/f'reference-{n}.png') for n in refs]
    proofs.append(ae.compare_original_outside_number(manifest,root,number,root/'original.png'))
    return manifest,proofs
