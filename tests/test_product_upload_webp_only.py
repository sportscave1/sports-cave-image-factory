"""Real encoders with isolated images; no provider calls or production sources."""
import io
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import image_factory as factory
import pytest
from tests.test_mockup_memory_pipeline import write_test_templates


def no_jpeg_saves():
    original=Image.Image.save
    def save(image,fp,format=None,**kwargs):
        assert str(format).upper()!='JPEG', 'Product Uploads must skip final JPEG encoding'
        return original(image,fp,format=format,**kwargs)
    return patch.object(Image.Image,'save',save)


def test_core_webps_and_previews_identical_without_final_jpeg_encoding(tmp_path):
    write_test_templates(tmp_path)
    source=tmp_path/'artwork.png'
    Image.new('RGB',(120,80),(20,40,80)).save(source)
    before=source.read_bytes()
    original=factory.generate_product_images('Test','Hockey',source,base_dir=tmp_path,output_root=tmp_path/'original')
    with no_jpeg_saves():
        current=factory.generate_product_images('Test','Hockey',source,base_dir=tmp_path,output_root=tmp_path/'current',export_jpg=False)
    assert len(current['assets'])==len(original['assets'])==5
    assert current['jpg_dir'] is None and not (current['run_dir']/factory.JPG_CACHE_FOLDER_NAME).exists()
    for old,new in zip(original['assets'],current['assets']):
        assert new['key']==old['key'] and new['jpg_path'] is None
        assert Path(old['jpg_path']).is_file() # standalone Mockups retains its original defaults
        for field in ('webp_path','preview_path','review_path'):
            assert Path(new[field]).name==Path(old[field]).name
            assert Path(new[field]).read_bytes()==Path(old[field]).read_bytes()
    assert source.read_bytes()==before


def test_lifestyle_import_preserves_webp_pixels_and_preview_without_jpeg(tmp_path):
    image=io.BytesIO()
    Image.new('RGB',(480,320),(40,80,120)).save(image,format='PNG')
    filename=sorted(factory.PRODUCT_PAGE_PROMPT_FILENAMES)[0]
    original=factory.save_lifestyle_mockup(tmp_path/'original','test','hockey',filename,image)
    with no_jpeg_saves():
        current=factory.save_lifestyle_mockup(tmp_path/'current','test','hockey',filename,image,export_jpg=False)
    assert current['jpg_path'] is None and Path(original['jpg_path']).is_file()
    assert not (tmp_path/'current'/factory.JPG_CACHE_FOLDER_NAME).exists()
    for key in ('webp_path','preview_path'):
        assert Path(current[key]).name==Path(original[key]).name
        assert Path(current[key]).read_bytes()==Path(original[key]).read_bytes()
    with Image.open(current['webp_path']) as output:
        assert output.size==(480,320) and output.getpixel((0,0))==(40,80,120)


@pytest.mark.parametrize('product_upload',[False,True])
def test_app_lifestyle_import_applies_webp_only_to_product_uploads(tmp_path,monkeypatch,product_upload):
    import app
    monkeypatch.setattr(app,'rebuild_result_artifacts',lambda value:value)
    monkeypatch.setattr(app,'record_activity_log',lambda *a,**kw:None)
    image=io.BytesIO()
    Image.new('RGB',(120,80),(40,80,120)).save(image,format='PNG')
    result=dict(run_dir=tmp_path,product_name='Test',product_slug='test',sport_slug='hockey',sport_category='Hockey')
    if product_upload:result['_product_upload_intake']='isolated-upload'
    filename=sorted(factory.PRODUCT_PAGE_PROMPT_FILENAMES)[0]
    result=app.save_uploaded_lifestyle_result(result,Path(filename),image)
    paths=result['lifestyle_mockup_paths'][filename]
    assert bool(paths.get('jpg_path')) is (not product_upload)
    assert Path(paths['webp_path']).is_file()


@pytest.mark.parametrize('missing_webp',[False,True])
def test_generation_job_accepts_missing_jpg_but_requires_webp(tmp_path,monkeypatch,missing_webp):
    from contextlib import contextmanager
    from threading import Semaphore
    import product_upload_jobs as jobs
    import product_upload_artwork as artwork
    import product_upload_intake
    from tests.test_product_upload_jobs import wait
    row=dict(id='webp-test',data={'source':dict(id='id:source',rev='one',content_hash='a'*64)})
    output=tmp_path/'render.webp';output.write_bytes(b'isolated fixture')
    record=dict(review_path=output,preview_path=output,webp_path=None if missing_webp else output,jpg_path=None)
    @contextmanager
    def prepared(*args):yield row,tmp_path
    def generate(*args,**kwargs):
        assert kwargs['export_jpg'] is False
        return dict(assets=[dict(record) for _ in range(5)],run_dir=tmp_path/'not-owned')
    monkeypatch.setattr(jobs,'JOBS',jobs.Jobs())
    monkeypatch.setattr(artwork,'prepared',prepared)
    monkeypatch.setattr(artwork,'current',lambda *a:None)
    monkeypatch.setattr(factory,'generate_product_images',generate)
    monkeypatch.setattr(factory,'cleanup_stale_temp_runs',lambda:None)
    monkeypatch.setattr(product_upload_intake.Intakes,'read',lambda *a:row)
    try:
        jobs.generate(None,row,'actor','Test','Hockey',lambda:None,tmp_path,Semaphore(1),lambda *a:[])
        result=wait(jobs.JOBS,'webp-test','actor','generate')
        assert result['state']==('Failed' if missing_webp else 'Ready')
    finally:jobs.JOBS.pool.shutdown()
