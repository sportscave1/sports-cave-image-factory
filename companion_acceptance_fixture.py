"""Synthetic 100-edition acceptance packet; never opens an authoritative PSD."""
import hashlib,json,random,zipfile
from pathlib import Path
from PIL import Image,ImageCms
import auto_editions as ae

def build(root,run,*,large=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    pixels=random.Random(20261020).randbytes(1024*768*3)
    with Image.frombytes('RGB',(1024,768),pixels) as image:
        image.save(root/'master.png',icc_profile=icc)
        image.save(root/'original.png',icc_profile=icc)
    def asset(name):return dict(name=name,sha256=ae.file_hash(root/name))
    patches={}
    for number in range(1,101):
        name=f'number-{number}.png'
        with Image.new('RGB',(32,16),(number,255-number,number*2%256)) as image:image.save(root/name,icc_profile=icc)
        patches[str(number)]=asset(name)
    manifest=dict(schema_version=1,strategy='photoshop_number_patches',
        source=ae.source_identity('gid://shopify/Product/999999999999999',dict(id='id:acceptance_'+run,rev=run,content_hash=ae.file_hash(root/'master.png',dropbox=True))),
        dimensions=[1024,768],source_dimensions=[1024,768],upscaled=False,number_region=[700,600,732,616],edition_total=100,
        master=asset('master.png'),patches=patches,
        colour_evidence=dict(icc_sha256=hashlib.sha256(icc).hexdigest(),pixels_converted=False))
    (root/'manifest.json').write_text(json.dumps(manifest))
    for number in (1,100):
        with ae.compose(manifest,root,number) as image:image.save(root/f'reference-{number}.png',icc_profile=icc)
    archive=root/'package.zip'
    with archive.open('wb') as stream:
        if large:
            # Legal ZIP preamble is explicit synthetic transport load, never
            # evidence of artwork compression or image quality. Bounded writes.
            from auto_editions_package_limits import LEGACY_BYTES
            remaining=LEGACY_BYTES+1;block=b'\0'*(1024*1024)
            while remaining:
                count=min(remaining,len(block));stream.write(block[:count]);remaining-=count
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as output:
            for path in root.iterdir():
                if path.suffix in ('.png','.json'):output.write(path,path.name)
    return archive

def validate_fixture(manifest,run):
    source=manifest['source']
    if (source['product_gid']!='gid://shopify/Product/999999999999999' or source['file_id']!='id:acceptance_'+run
        or source['revision']!=run or manifest['edition_total']!=100 or manifest['dimensions']!=[1024,768]
        or manifest['number_region']!=[700,600,732,616] or not manifest.get('colour_evidence')):
        raise ValueError('Only the isolated synthetic acceptance identity is permitted.')
