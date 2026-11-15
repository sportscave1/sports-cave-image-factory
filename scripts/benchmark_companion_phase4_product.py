"""Current v3 server decode/WEBP-only mockups; immutable PSD and no providers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def benchmark(source,output):
    import auto_editions as ae
    import image_factory as factory
    import product_upload_artwork as candidate
    from PIL import Image,ImageCms
    from scripts.benchmark_companion_phase1 import Sample
    import requests
    source=Path(source);output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'output'):raise ValueError('New task-local output required.')
    output.mkdir(parents=True)
    released=types.ModuleType('released_artwork');released.__file__=str(ROOT/'product_upload_artwork.py')
    exec(compile(subprocess.check_output(['git','show','58569c66:product_upload_artwork.py'],cwd=ROOT),released.__file__,'exec'),released.__dict__)
    config_root=Path.home()/'Documents/SportsCaveAutoEditions/colour-configuration'
    config=dict(policies=json.loads((config_root/'policies.json').read_text()),memberships=json.loads((config_root/'memberships.json').read_text()),default_group='')
    row=dict(data=dict(source=dict(id='id:u1tYiAa2O-AAAAAAAACGzQ',rev='0165e3b47576fc1000000036d367e13',
        content_hash='ac5aa7d68a7265b76e22a95be0d3e684995599229d2c90c64d00f7927288e013')))
    before=ae.file_hash(source);assert before=='ec598df55adbb48e0b2821b430121cf87663e7e4b71ab49a457c84fef3c57d24'
    fixed_profile=ImageCms.createProfile('sRGB') # Same ICC creation timestamp for encoding comparison.
    original_save=Image.Image.save;result=dict(source_bytes=source.stat().st_size,local_only=True,workflow='v3 server',cache='Cold derived cache; verified resident PSD, warm OS reads',runs=[],comparisons=[])
    try:
        with patch('auto_editions_colour_store.configuration',return_value=config),patch('PIL.ImageCms.createProfile',return_value=fixed_profile),patch('requests.sessions.Session.send',side_effect=AssertionError('No external benchmark HTTP.')):
            for pair in range(3):
                values={}
                for variant in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
                    directory=output/(str(pair)+variant[0]);directory.mkdir();png=directory/'artwork.png';timings={}
                    def save(image,fp,*args,**kwargs):
                        if Path(fp)!=png:return original_save(image,fp,*args,**kwargs)
                        if variant=='candidate':kwargs['compress_level']=1
                        start=time.perf_counter()
                        try:return original_save(image,fp,*args,**kwargs)
                        finally:timings['png_save_seconds']=time.perf_counter()-start
                    with Sample() as sample,patch.object(Image.Image,'save',save),tempfile.TemporaryDirectory(prefix='sc-v3-p4-') as temp:
                        cpu=time.process_time();started=time.perf_counter()
                        begin=time.perf_counter();assert ae.file_hash(source,dropbox=True)==row['data']['source']['content_hash'];timings['source_verification_seconds']=time.perf_counter()-begin
                        begin=time.perf_counter();colour=(released if variant=='baseline' else candidate).decode(source,png,row,None);timings['decode_seconds']=time.perf_counter()-begin
                        begin=time.perf_counter();factory.create_preview_file(png,directory,'preview.webp');timings['prepared_preview_seconds']=time.perf_counter()-begin
                        begin=time.perf_counter();hashes={n:ae.file_hash(directory/n) for n in ('artwork.png','preview.webp')};timings['cache_hash_seconds']=time.perf_counter()-begin
                        begin=time.perf_counter();images=factory.generate_product_images('Pinstripe Immortals - Ruth & Mantle','Baseball',png,base_dir=ROOT,output_root=Path(temp),final_prompt_items=[],export_jpg=False);timings['core_mockups_seconds']=time.perf_counter()-begin
                        timings['local_processing_seconds']=time.perf_counter()-started;timings['local_processing_cpu_seconds']=time.process_time()-cpu
                        assets=[]
                        for asset in images['assets']:
                            assert not asset['jpg_path']
                            assets.append(dict(key=asset['key'],**{key:ae.file_hash(asset[key]) for key in ('webp_path','review_path','preview_path')}))
                        assert len(assets)==5
                        with Image.open(png) as image:
                            image.load();pixels=hashlib.sha256(image.tobytes()).hexdigest();profile=hashlib.sha256(image.info['icc_profile']).hexdigest();dimensions=list(image.size)
                    value=dict(pair=pair,variant=variant,timings=timings,resources=sample.result,png_bytes=png.stat().st_size,
                        assets=assets,pixels=pixels,icc_sha256=profile,dimensions=dimensions,colour=colour,hashes=hashes)
                    result['runs'].append(value);values[variant]=value
                    (output/'measurements.json').write_text(json.dumps(result,indent=2))
                    print(pair,variant,timings['local_processing_seconds'],timings['png_save_seconds'],value['png_bytes'],flush=True)
                a,b=values['baseline'],values['candidate'];assert a['assets']==b['assets'] and a['pixels']==b['pixels'] and a['icc_sha256']==b['icc_sha256'] and a['dimensions']==b['dimensions']
                result['comparisons'].append(dict(all_five_webps_and_previews_byte_exact=True,internal_png_pixels_and_icc_exact=True))
        assert ae.file_hash(source)==before
        return result
    finally:(output/'measurements.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();benchmark(args.source,args.output)
