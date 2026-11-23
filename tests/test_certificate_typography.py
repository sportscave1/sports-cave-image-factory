from pathlib import Path
import re
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
    expected=display_title(title)
    if len(layout)==3:
        expected=re.sub(r'\s*[–—;:]\s*|\s+-\s+', ' ', expected).strip()
    assert expected==' '.join(entry['text'] for entry in layout[:-1])

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


@pytest.mark.parametrize('size', [(2835,2004),(1200,848),(3508,2480)])
@pytest.mark.parametrize('title', ['The Seventh — Nolan Ryan Wall Art', 'The Dynasty — Troy Aikman & Emmitt Smith Wall Art'])
def test_revised_master_has_equal_space_above_and_below_complete_text_block(size,title):
    with Image.new('RGB',size,'white') as image:
        layout=text_layout(ImageDraw.Draw(image),size,title,27,100)
    # Independently measured printed landmarks in the revised 2835x2004 JPG.
    ornament_bottom, handcrafted_top = 1292/2004*size[1], 1740/2004*size[1]
    above=layout[0]['bounds'][1]-ornament_bottom
    below=handcrafted_top-layout[-1]['bounds'][3]
    assert above==pytest.approx(below,abs=1)
    assert above>=24/2004*size[1]
    assert layout[-1]['text']=='No. 027 of 100'


def test_two_line_title_keeps_full_athlete_names_together_at_existing_font_size():
    with Image.new('RGB',(2835,2004),'white') as image:
        layout=text_layout(ImageDraw.Draw(image),image.size,'The Dynasty — Troy Aikman & Emmitt Smith Wall Art',30,100)
    assert [item['text'] for item in layout]==['The Dynasty','Troy Aikman & Emmitt Smith','No. 030 of 100']
    assert layout[0]['font'].size==100
    assert layout[1]['font'].size==80
    assert layout[1]['font'].path.endswith('SourceSerif4-Regular.ttf')
    assert layout[1]['fill']==(45,45,45)
    assert layout[0]['fill']==layout[2]['fill']==(0,0,0)
    assert layout[1]['bounds'][1]>layout[0]['bounds'][3]
    assert layout[2]['bounds'][1]>layout[1]['bounds'][3]


def test_two_line_title_without_divider_avoids_a_single_word_orphan():
    with Image.new('RGB',(2835,2004),'white') as image:
        layout=text_layout(ImageDraw.Draw(image),image.size,'The Greatest Sporting Legends of Our Extraordinary Generation Wall Art',1,100)
    assert len(layout)==3
    assert all(len(item['text'].split())>1 for item in layout[:2])
    widths=[item['bounds'][2]-item['bounds'][0] for item in layout[:2]]
    assert min(widths)/max(widths)>.7


@pytest.mark.parametrize('separator', [' — ', ' – ', ' - ', '; ', ': '])
def test_two_line_separators_are_replaced_by_the_subtitle_break(separator):
    title='The Dynasty'+separator+'Troy Aikman & Emmitt Smith Wall Art'
    with Image.new('RGB',(2835,2004),'white') as image:
        layout=text_layout(ImageDraw.Draw(image),image.size,title,30,100)
    assert [item['text'] for item in layout[:2]]==['The Dynasty','Troy Aikman & Emmitt Smith']


def test_subtitle_preserves_hyphenated_athlete_names():
    with Image.new('RGB',(2835,2004),'white') as image:
        layout=text_layout(ImageDraw.Draw(image),image.size,'The Greatest Sporting Legacy — Jean-Luc Smith and Karl-Anthony Towns Wall Art',27,100)
    assert layout[1]['text']=='Jean-Luc Smith and Karl-Anthony Towns'
    assert layout[1]['font'].size<layout[0]['font'].size
