"""Immutable artwork viewing only. Never used for approval or technical readiness."""
from pathlib import Path
import re
from PIL import Image
import auto_editions as ae


def evidence(record):
    m=record['manifest'];ae.validate_manifest(m)
    if record['hash']!=ae.fingerprint(m):raise ValueError('Preparation identity changed.')
    colour=m.get('colour_evidence')
    if colour and (colour.get('pixels_converted') is not False
            or not re.fullmatch('[a-f0-9]{64}',str(colour.get('icc_sha256')))):
        raise ValueError('Current source colour evidence required.')
    proofs=record.get('proofs') or []
    if (not proofs or any(p.get('preparation_hash')!=record['hash'] for p in proofs)
            or not any(p.get('outside_number_exact') is True for p in proofs)
            or not {1,m['edition_total']}<={p.get('number') for p in proofs if p.get('pixel_exact') is True}):
        raise ValueError('Current artwork-preservation proofs required for this preview.')
    plaque=ae.bounds(m.get('plaque_bounds'),m['dimensions']);r=m['number_region']
    if not (plaque[0]<=r[0]<r[2]<=plaque[2] and plaque[1]<=r[1]<r[3]<=plaque[3]) or m.get('source_modified') is not False:
        raise ValueError('Plaque geometry or source preservation needs attention.')
    receipts=record.get('receipts') or {};rows=receipts.get('assets') or []
    names={a['name'] for a in [m['master'],*m['patches'].values()]}
    if (receipts.get('preparation_hash')!=record['hash'] or len(rows)!=len(names)
            or {a.get('name') for a in rows}!=names or len({a.get('file_id') for a in rows})!=len(rows)
            or any(not str(a.get('file_id','')).startswith('id:') or not a.get('revision')
                or ('bytes' in a and (type(a['bytes']) is not int or a['bytes']<=0)) for a in rows)):
        raise ValueError('Immutable preview asset identities required.')
    return m


def inspect_asset(root,asset,expected,fetch,digest,receipts,expected_icc=None):
    from auto_editions_cloud import DropboxAssets
    path=Path(root)/asset['name'];fetch(digest,asset,path)
    ae.asset_path(root,asset)  # Mandatory exact manifest SHA, even on cached files.
    size=path.stat().st_size
    receipt=next(r for r in receipts['assets'] if r['name']==asset['name'])
    if not 0<size<=DropboxAssets.MAX_ASSET_BYTES or ('bytes' in receipt and size!=receipt['bytes']):
        raise ValueError('Prepared preview size changed.')
    with Image.open(path) as image:
        if image.format!='PNG' or image.mode!='RGB' or list(image.size)!=expected:
            raise ValueError('Prepared preview geometry or mode changed.')
        profile=image.info.get('icc_profile',b'')
        if expected_icc and not profile:raise ValueError('Recorded ICC profile missing from preview bytes.')
        if profile:
            from auto_editions_colour_source import profile_info
            actual=profile_info(profile)
            if expected_icc and actual['sha256']!=expected_icc:raise ValueError('Source ICC evidence differs from prepared bytes.')
    return profile
