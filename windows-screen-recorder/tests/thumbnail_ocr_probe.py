"""Read-only candidate OCR worker. Dependencies remain in an isolated test folder."""
import json
import hashlib
import sys
from pathlib import Path

request_path, result_path = map(Path, sys.argv[1:3])
request = json.loads(request_path.read_text(encoding='utf-8-sig'))
sys.path.insert(0, request['library'])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rapidocr import RapidOCR
from PIL import Image
from desktop_recorder.thumbnail_caption import unique_caption

try:
    models = Path(request['library']) / 'rapidocr' / 'models'
    pinned = {
        'Det': ('PP-OCRv6_det_small.onnx','090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'),
        'Cls': ('ch_ppocr_mobile_v2.0_cls_mobile.onnx','e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c'),
        'Rec': ('PP-OCRv6_rec_small.onnx','6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884'),
    }
    # Preserve physical desktop resolution; default 2000px downsampling blurs
    # 2560px-monitor caption text before recognition.
    params = {'Global.log_level':'error', 'Global.max_side_len':4096}
    for stage,(name,digest) in pinned.items():
        path = models / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Local OCR model integrity check failed.')
        params[stage+'.model_path'] = str(path)
    engine = RapidOCR(params=params)
    result = engine(request['image'])
    rows = [dict(box=box.tolist(), text=text, score=float(score))
            for box,text,score in zip(result.boxes,result.txts,result.scores)]
    with Image.open(request['image']) as image:
        answer = unique_caption(rows, request['title'], *image.size)
    answer['ok'] = True
except Exception as error:
    answer = dict(ok=False, error=str(error)[:240])
result_path.write_text(json.dumps(answer), encoding='utf-8')
