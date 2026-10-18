"""Owner-reviewed presentation corrections on disposable exports only.

Exact source identity is mandatory. No general alpha flattening, plaque guessing,
font substitution or original PSD writes are provided by this module.
"""
import shutil
from PIL import Image,ImageChops
from auto_editions_role_evidence import resolution


def require_export_evidence(manifest):
    selected=resolution(manifest['source'])
    if not selected:return
    proof=manifest.get('artwork_recovery') or {}
    if selected.get('hidden_number') and (proof.get('hidden_number')!=selected['hidden_number'] or proof.get('outside_plaque_exact') is not True):
        raise ValueError('Reviewed obsolete-number correction and outside-plaque pixel proof required.')
    if selected.get('opaque_backing') and (proof.get('opaque_backing')!=selected['opaque_backing'] or proof.get('unbacked_exports_preserved') is not True):
        raise ValueError('Verified owner-approved opaque presentation evidence required.')


def verify_hidden(root,report,selected):
    if selected.get('hidden_number'):
        scale=report['preparation_geometry']['scale']
        box=[int(v*scale) for v in selected['plaque']['bounds_px']]
        with Image.open(root/'uncorrected.png') as before,Image.open(root/'original.png') as after:
            if before.size!=after.size:raise ValueError('Reviewed correction changed canvas geometry.')
            a=before.convert('RGBA');b=after.convert('RGBA');w,h=a.size
            strips=[(0,0,w,box[1]),(0,box[3],w,h),(0,box[1],box[0],box[3]),(box[2],box[1],w,box[3])]
            for region in strips:
                if any(band.getbbox() for band in ImageChops.difference(a.crop(region),b.crop(region)).split()):
                    raise ValueError('Reviewed number correction changed artwork outside the approved plaque.')


def verify_package(root,manifest):
    require_export_evidence(manifest)
    selected=resolution(manifest['source'])
    if selected:verify_hidden(root,manifest,selected)


def verify_exports(root,report,source,names):
    selected=resolution(source)
    if not selected:return None
    result={}
    hidden=selected.get('hidden_number')
    backing=selected.get('opaque_backing')
    backup=root.parent/'artwork-recovery-backups'/root.name
    if hidden or backing:backup.mkdir(parents=True,exist_ok=False)
    if hidden:
        verify_hidden(root,report,selected)
        shutil.copyfile(root/'uncorrected.png',backup/'uncorrected.png')
        result['hidden_number']=hidden
        result['outside_plaque_exact']=True
    if backing:
        if backing['rgb']!=[0,0,0] or not backing.get('approval') or backing['comparison']['outside_mae']>=1 or backing['comparison']['outside_rmse']>=2:
            raise ValueError('Verified owner-approved backing evidence is unavailable.')
        backup=backup/'unbacked-exports';backup.mkdir(exist_ok=False)
        changed=[]
        for name in names:
            path=root/name
            with Image.open(path) as im:
                icc=im.info.get('icc_profile');dpi=im.info.get('dpi')
                if not icc:raise ValueError('Approved backing requires the preserved embedded output ICC.')
                if im.mode=='RGB':continue
                if im.mode!='RGBA':raise ValueError('Approved backing requires an RGB source export.')
                shutil.copyfile(path,backup/name)
                out=Image.new('RGBA',im.size,tuple(backing['rgb'])+(255,));out.alpha_composite(im)
                options={'icc_profile':icc}
                if dpi:options['dpi']=dpi
                out.convert('RGB').save(path,**options)
            with Image.open(path) as checked:
                if checked.mode!='RGB' or checked.info.get('icc_profile')!=icc:
                    raise ValueError('Approved backing changed the output ICC or opacity.')
            changed.append(name)
        result['opaque_backing']=backing
        result['backed_exports']=changed
        result['unbacked_exports_preserved']=True
    return result or None
