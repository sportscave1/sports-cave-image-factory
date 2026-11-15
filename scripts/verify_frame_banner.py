"""Read-only live product verification. Writes local artifacts; never sends/upload assets.

Run from repository root with .venv Python. Browser comparison uses the captured
unmodified theme renderer, not a reimplementation of its crop calculation.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_frame_banner_assets import fetch,WallRoot,cdn_image,image_identity,crop_image,frame_name
from crm_frame_banner_template import resolve,source
from unittest.mock import patch


def run():
    output=Path('artifacts/frame-banner');output.mkdir(parents=True,exist_ok=True)
    rows=[];examples=[]
    for slug in ('peter-brock-bathurst-wall-art','jack-brabham-1959-framed-sports-art'):
        url='https://www.sportscaveshop.com/products/'+slug
        product=json.loads(fetch(url+'.js',2*1024*1024))
        parser=WallRoot();parser.feed(fetch(url+'?section_id=sc-wall-preview',2*1024*1024).decode('utf-8'))
        root=next(r for r in parser.roots if r.get('data-product-id')==str(product['id']))
        rendered={}
        for variant in product['variants']:
            frame=frame_name(variant['title'])
            if not frame:continue
            original=(variant.get('featured_image') or {}).get('src','')
            selected='black' if frame=='unframed' else frame
            wall=root.get('data-'+selected+'-url','')
            if wall.startswith('//'):wall='https:'+wall
            matches=bool(image_identity(original) and image_identity(original)==image_identity(wall))
            rows.append(dict(product=product['title'],variant=variant['title'],variant_id=variant['id'],
                             checkout_variant_image=original,wall_source=wall,exact_source_match=matches))
            if frame not in rendered:
                filename=slug+'-'+frame
                payload=fetch(wall);(output/(filename+'-source.png')).write_bytes(payload)
                (output/(filename+'-crop.jpg')).write_bytes(crop_image(payload,frame))
                examples.append(dict(name=product['title']+' / '+frame,frame=frame,filename=filename,
                                     exact_source_match=matches))
                rendered[frame]=True
        first=product['variants'][0]
        item=dict(title=product['title'],variant=first['title'],image=first['featured_image']['src'],
                  product_id=str(product['id']),variant_id=str(first['id']),product_url=url)
        with patch('crm_frame_banner_assets.prepare',return_value='https://example.test/banner.jpg'):
            html=resolve({'custom_html':source()},{'items':[item]})['custom_html']
        html=html.replace('https://example.test/banner.jpg',slug+'-black-crop.jpg')
        (output/(slug+'-email.html')).write_text('<meta name="viewport" content="width=device-width, initial-scale=1"><div style="max-width:600px;margin:auto">'+html+'</div>',encoding='utf-8')
    (output/'verified-products.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    (output/'examples.json').write_text(json.dumps(examples,indent=2),encoding='utf-8')
    print(json.dumps({'variants':len(rows),'source_matches':sum(r['exact_source_match'] for r in rows),'comparisons':len(examples)}))


if __name__=='__main__':run()
