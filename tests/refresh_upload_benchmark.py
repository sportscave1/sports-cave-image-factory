"""CPU-only unchanged-upload benchmark against the pre-repair function."""
import ast
import copy
import io
import json
from pathlib import Path
import statistics
import subprocess
import time
from unittest.mock import patch
from PIL import Image
import ads_page as ads
from tests.fixtures.refresh_ui import ready_carousel
from tests.test_posting_import_csv import FakeUpload


def main():
    source=subprocess.check_output(['git','show','b274b05:ads_page.py']).decode('utf-8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_process_ads_image_upload')
    namespace=vars(ads).copy()
    exec(compile(ast.Module(body=[node],type_ignores=[]),'pre-repair-upload','exec'),namespace)
    image=Image.effect_noise((2048,2048),80).convert('RGB')
    output=io.BytesIO();image.save(output,'PNG');data=output.getvalue()
    measurements={'source_bytes':len(data),'iterations':60,'scope':'Unchanged upload CPU only; no network or artificial latency'}
    for label,method in [('before',namespace['_process_ads_image_upload']),('after',ads._process_ads_image_upload)]:
        result,workflow=ready_carousel();spec=ads._result_image_slots(result)[0]
        upload=FakeUpload(data,name='fixture-noise.png',file_id='fixture-upload')
        timings=[]
        with patch.object(ads.st,'session_state',{}):
            method(result,workflow,spec,upload)
            original=bytes(workflow['slots'][spec['id']]['data'])
            for _ in range(60):
                started=time.perf_counter();method(result,workflow,spec,upload);timings.append((time.perf_counter()-started)*1000)
            assert workflow['slots'][spec['id']]['data']==original
        measurements[label+'_median_ms']=round(statistics.median(timings),6)
    Path('tmp/refresh-upload-benchmark.json').write_text(json.dumps(measurements,indent=2),encoding='utf-8')
    print(json.dumps(measurements))


if __name__=='__main__':main()
