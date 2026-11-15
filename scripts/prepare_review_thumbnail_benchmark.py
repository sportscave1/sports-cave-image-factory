"""Explicit synthetic PNG benchmark exports. Never opens Photoshop or a provider."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).parents[1]))
import auto_editions as ae
from PIL import Image,ImageDraw,ImageCms,ImageFont


def create(root):
    root=Path(root)
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for index,(width,height) in enumerate(((11340,8016),(6000,4000),(2835,2004))):
        target=root/str(index);target.mkdir(parents=True,exist_ok=True)
        if (target/'record.json').exists():continue
        start=time.perf_counter();region=[width*7//10,height*85//100,width*85//100,height*9//10]
        plaque=[width*6//10,height*8//10,width*95//100,height*95//100]
        with Image.effect_noise((max(1,width//8),max(1,height//8)),45).convert('RGB').resize((width,height),Image.Resampling.BILINEAR) as master:
            draw=ImageDraw.Draw(master);draw.rectangle(tuple(plaque),fill='#12304b',outline='white',width=max(1,width//500))
            draw.text((width//10,height//10),'SYNTHETIC REVIEW TIMING FIXTURE',fill='white',font=ImageFont.truetype('arial.ttf',height//35))
            master.save(target/'master.png',icc_profile=profile,compress_level=1)
        for number in (1,2):
            with Image.new('RGB',(region[2]-region[0],region[3]-region[1]),'#12304b') as patch:
                ImageDraw.Draw(patch).text((5,5),f'{number:03} / 002',font=ImageFont.truetype('arial.ttf',height//40),fill='white')
                patch.save(target/f'number-{number}.png',icc_profile=profile)
        def asset(name):return dict(name=name,sha256=ae.file_hash(target/name))
        m=dict(schema_version=1,strategy='photoshop_number_patches',source=ae.source_identity('gid://shopify/Product/'+str(900001+index),dict(id='id:synthetic-'+str(index),rev='a1',content_hash='a'*64)),
            dimensions=[width,height],source_dimensions=[width,height],upscaled=False,number_region=region,plaque_bounds=plaque,edition_total=2,source_modified=False,
            master=asset('master.png'),patches={str(n):asset(f'number-{n}.png') for n in (1,2)})
        digest=ae.fingerprint(m)
        # These are explicitly synthetic validation fixtures, not Photoshop proofs
        # or production receipts. Real artwork is never relabelled as sRGB.
        proofs=[dict(number=n,preparation_hash=digest,pixel_exact=True,outside_number_exact=True) for n in (1,2)]
        receipts=dict(preparation_hash=digest,assets=[dict(name=a['name'],file_id='id:fixture-'+str(index)+'-'+a['name'],revision='synthetic-transport',bytes=(target/a['name']).stat().st_size) for a in [m['master'],*m['patches'].values()]])
        (target/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
        (target/'record.json').write_text(json.dumps(dict(hash=digest,manifest=m,proofs=proofs,receipts=receipts)),encoding='utf-8')
        print(json.dumps(dict(synthetic_sample=index,dimensions=m['dimensions'],creation_seconds=round(time.perf_counter()-start,2))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    create(parser.parse_args().output)
