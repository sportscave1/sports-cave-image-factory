from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageChops
import certificate_service as service
from certificate_typography import text_layout, display_number, display_title, TEXT_BAND

@pytest.mark.parametrize('number,total,label',[(1,100,'No. 001 of 100'),(27,100,'No. 027 of 100'),(30,100,'No. 030 of 100'),(100,100,'No. 100 of 100'),(1000,1500,'No. 1000 of 1500')])
def test_exact_allocated_number_is_formatted_without_increment(number,total,label):
    assert display_number(number,total)==label
    assert service.format_edition_number(number,total)==f'#{number:03d}/{total}'

@pytest.mark.parametrize('size',[(2835,2004),(1200,848),(3508,2480)])
@pytest.mark.parametrize('title',['The Seventh — Nolan Ryan Wall Art','The Dynasty – Troy Aikman & Emmitt Smith Wall Art','A Long Collector Edition Celebrating an Extraordinary Sporting Legacy — Giannis Antetokounmpo and the Milwaukee Bucks Wall Art'])
def test_text_block_is_centered_between_ornament_and_handcrafted_without_clipping(size,title):
    with Image.new('RGB',size,'white') as image:
        layout=text_layout(ImageDraw.Draw(image),size,title,30,100)
    bounds=[entry['bounds'] for entry in layout]
    assert (bounds[0][1]+bounds[-1][3])/2==pytest.approx(sum(TEXT_BAND)/2*size[1],abs=1)
    for left,top,right,bottom in bounds:
        assert (left+right)/2==pytest.approx(size[0]/2,abs=1)
        assert left>=size[0]*.21-1 and right<=size[0]*.79+1
        assert top>=size[1]*TEXT_BAND[0] and bottom<=size[1]*TEXT_BAND[1]
    assert layout[-1]['text']=='No. 030 of 100'
    assert display_title(title)==' '.join(entry['text'] for entry in layout[:-1])

@pytest.mark.parametrize('path',[service.CERTIFICATE_TEMPLATE_PRINT_PATH,service.CERTIFICATE_TEMPLATE_PREVIEW_PATH])
def test_blank_master_border_and_body_are_untouched(path):
    with Image.open(path) as source:
        original=source.convert('RGB')
    with service.render_template_certificate_image(product_title='The Seventh — Nolan Ryan Wall Art',edition_number=30,edition_total=100,template_path=path) as result:
        box=ImageChops.difference(original,result).getbbox()
        assert box is not None
        assert box[1]>=original.height*TEXT_BAND[0]
        assert box[3]<=original.height*TEXT_BAND[1]
    original.close()

def test_actual_pdf_jpg_and_preview_use_the_same_number_and_master(tmp_path):
    args=dict(product_title='The Seventh — Nolan Ryan Wall Art',edition_number=30,edition_total=100,order_name='LOCAL-PROOF',shopify_handle='local-proof')
    paths=[service.generate_template_certificate_pdf(tmp_path,**args),service.generate_certificate_print_jpg(tmp_path,**args),service.generate_certificate_preview_webp(tmp_path,**args)]
    assert Path(paths[0]).read_bytes().startswith(b'%PDF')
    with Image.open(paths[1]) as image:
        assert image.size==(3508,2480)
        assert image.info['dpi']==(300,300)
    with Image.open(paths[2]) as image:
        assert image.width==1200 and abs(image.width/image.height-2835/2004)<.002
    assert all('030' in Path(path).name for path in paths)
