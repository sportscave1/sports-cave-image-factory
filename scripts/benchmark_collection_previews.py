"""Offline synthetic benchmark; never reads customer records or remote assets."""
import io
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from collector_collection_offers import render_certificate_frame
from collector_preview_cache import PreviewPipeline


def benchmark():
    image = Image.new('RGB', (1200, 848), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((25, 25, 1175, 823), outline='black', width=5)
    draw.text((400, 500), 'Synthetic issued certificate - No. 027 of 100', fill='black')
    source = io.BytesIO()
    image.save(source, 'WEBP', quality=90)
    image.close()
    report = {'scope': 'Offline synthetic source, real Pillow/templates; excludes network, auth and database time', 'widths': {}}
    asset = dict(owner_hash='synthetic-owner', certificate_row_id=1, kind='preview', storage='fixture', key='issued-v1')
    for width in (400, 1000):
        calls = {'fetch': 0, 'render': 0}
        def fetch(_):
            calls['fetch'] += 1
            return source.getvalue()
        def render(content, color, size):
            calls['render'] += 1
            return render_certificate_frame(content, color, output_width=size)
        pipeline = PreviewPipeline(fetch=fetch, render=render)
        def three_colours():
            start = time.perf_counter()
            outputs = [pipeline.framed(asset, c, width, lambda: 'fixture-only') for c in ('black', 'oak', 'white')]
            return (time.perf_counter() - start) * 1000, outputs
        cold_ms, outputs = three_colours()
        warm_ms = [three_colours()[0] for _ in range(5)]
        assert calls == {'fetch': 1, 'render': 3}
        report['widths'][str(width)] = dict(cold_three_colours_ms=round(cold_ms, 3), warm_three_colours_median_ms=round(statistics.median(warm_ms), 3), output_bytes=sum(map(len, outputs)), **calls)
    return report


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2))
