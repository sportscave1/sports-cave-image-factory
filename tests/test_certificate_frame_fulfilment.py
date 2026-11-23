"""Synthetic certificates and disposable SQL only; never supplier writes."""
import io,json,uuid
from copy import deepcopy
from pathlib import Path
import pytest
from PIL import Image,JpegImagePlugin
import certificate_frame_fulfilment as frames
from test_auto_editions_jobs import database

REF='12345678-1234-4234-8234-123456789012'
ORDER='gid://shopify/Order/99'
VARIANT='gid://shopify/ProductVariant/68066069938483'

@pytest.fixture
def paid(database):
    jobs,q=database
    q.execute("CREATE TABLE app_settings(key text primary key,value jsonb,updated_at timestamptz default now()); CREATE TABLE edition_orders(id bigint primary key); CREATE TABLE collector_frame_requests(request_reference text primary key,status text,framed_shopify_order_id text,shopify_customer_id text,frame_variant_id text,frame_product_id text,certificate_row_id bigint,certificate_id text,edition_number int,edition_limit int,artwork_title text,original_shopify_order_id text); CREATE TABLE certificates(id bigint primary key,certificate_id text,shopify_order_id text,shopify_customer_id text,edition_number int,edition_limit int,certificate_pdf_url text,certificate_preview_image_url text); CREATE TABLE shopify_orders(shopify_order_id text primary key,raw_json jsonb)")
    q.execute("INSERT INTO collector_frame_requests VALUES(%s,'ordered',%s,'gid://shopify/Customer/101',%s,'gid://shopify/Product/10332579103027',12,'SC-027',27,100,'Synthetic edition','gid://shopify/Order/44')",(REF,ORDER,VARIANT))
    q.execute("INSERT INTO certificates VALUES(12,'SC-027','gid://shopify/Order/44','gid://shopify/Customer/101',27,100,'https://cdn.shopify.com/certificate.pdf','https://cdn.shopify.com/preview.png')")
    raw=dict(id=99,name='#SC99',financial_status='paid',customer={'id':101},shipping_address=dict(name='Synthetic Owner',address1='1 Test Street',city='Test',province='NSW',zip='2000',country_code='AU'),line_items=[dict(id=555,variant_id=VARIANT,sku='SC-FCC-A4-OAK',quantity=1,properties=[dict(name='_sports_cave_frame_request',value=REF)])])
    q.execute('INSERT INTO shopify_orders VALUES(%s,%s::jsonb)',(ORDER,json.dumps(raw)))
    return jobs,q,raw

def test_paid_retry_preserves_original_number_and_normal_artwork(paid,monkeypatch):
    jobs,q,raw=paid
    raw['line_items'].append(dict(id=556,sku='NORMAL-ART',quantity=1))
    assert frames.ingest_paid(raw,jobs.connect)==1
    assert frames.ingest_paid(raw,jobs.connect)==1
    q.execute('SELECT count(*) AS n FROM app_settings'); assert q.fetchone()['n']==1
    q.execute('SELECT count(*) AS n FROM edition_orders'); assert q.fetchone()['n']==0
    aid=frames.allocation_id(ORDER,'gid://shopify/LineItem/555',1)
    current,_=frames.unit(aid,jobs.connect)
    assert current['edition_number']==27 and current['frame_color']=='Oak'
    job=frames.job_for(aid,jobs.connect);assert job['number']==27 and job['total']==100
    jobs.enqueue(job,'synthetic'); assert jobs.read_bound(job['id'],aid)[1]['id']==aid
    from auto_editions_store import Preparations
    assert Preparations(jobs.connect).unit(aid)[0]==current
    monkeypatch.setenv('COLLECTOR_VAULT_ASSET_SIGNING_SECRET','synthetic-test-only')
    normal={'shopify_order_id':ORDER,'shopify_line_item_id':'556','product_title':'Untouched artwork'}
    rows=frames.merge_rows([normal],jobs.connect)
    assert normal in rows and len(rows)==2 and rows[1]['edition_order_id']==aid
    assert 'certificate.pdf' in job['source']['asset']['url']
    import orders_page
    normalized=orders_page._normalise_row(rows[1])
    assert normalized['order']=='#SC99' and normalized['product'].startswith('Framed Collector Certificate')
    assert normalized['edition_order_id']==str(aid)

@pytest.mark.parametrize('change',[lambda r:r.update(cancelled_at='now'),lambda r:r.update(refunds=[{}]),lambda r:r.update(customer={'id':202}),lambda r:r['line_items'][0].update(variant_id='wrong')])
def test_changed_paid_line_blocked(paid,change):
    jobs,q,raw=paid;frames.ingest_paid(raw,jobs.connect)
    change(raw);q.execute('UPDATE shopify_orders SET raw_json=%s::jsonb',(json.dumps(raw),))
    with pytest.raises(ValueError):frames.unit(frames.allocation_id(ORDER,'gid://shopify/LineItem/555',1),jobs.connect)
    assert frames.merge_rows([{'product_title':'Normal row'}],jobs.connect)==[{'product_title':'Normal row'}]

def test_normalized_mirror_and_quantity_units(paid):
    jobs,q,raw=paid;raw['line_items'][0]['quantity']=2
    frames.ingest_paid(raw,jobs.connect)
    raw['shopify_customer_id']='gid://shopify/Customer/101';raw.pop('customer')
    raw['line_items'][0]['shopify_line_item_id']='gid://shopify/LineItem/555';raw['line_items'][0].pop('id')
    q.execute('UPDATE shopify_orders SET raw_json=%s::jsonb',(json.dumps(raw),))
    for ordinal in (1,2):assert frames.unit(frames.allocation_id(ORDER,'gid://shopify/LineItem/555',ordinal),jobs.connect)[0]['unit_ordinal']==ordinal

def test_upscale_keeps_certificate_and_print_encoding(tmp_path):
    stream=io.BytesIO()
    with Image.new('RGB',(700,500),'white') as image:image.save(stream,'PNG')
    path=tmp_path/'print.jpg';result=frames.render(stream.getvalue(),'image/png',path)
    assert result['scale']==4 and result['dimensions']==[2800,2000]
    with Image.open(path) as image:
        assert image.info['dpi']==(300,300) and image.info['icc_profile']
        assert JpegImagePlugin.get_sampling(image)==0
        assert all(v==1 for table in image.quantization.values() for v in table)

def test_single_page_pdf_render(tmp_path):
    import pypdfium2 as pdfium
    doc=pdfium.PdfDocument.new();doc.new_page(72,50)
    stream=io.BytesIO();doc.save(stream);doc.close()
    result=frames.render(stream.getvalue(),'application/pdf',tmp_path/'pdf.jpg')
    assert result['source_dimensions']==[300,209]

def test_uuid_response_is_json_serializable():
    import collector_vault_api as api
    reference=uuid.uuid4()
    response=api._json({'request_reference':reference})
    assert json.loads(response.body)['request_reference']==str(reference)

@pytest.mark.parametrize('color,sku',[('Black','SC-FCC-A4-BLK'),('Oak','SC-FCC-A4-OAK'),('White','SC-FCC-A4-WHT')])
def test_small_colour_and_exact_source_join_normal_preparation(paid,monkeypatch,color,sku):
    import auto_editions_runtime as runtime
    import auto_editions_cloud as cloud
    import prodigi_preparation as prep
    import os_pages
    jobs,q,raw=paid;raw['line_items'][0]['sku']=sku
    frames.ingest_paid(raw,jobs.connect)
    aid=frames.allocation_id(ORDER,'gid://shopify/LineItem/555',1)
    job=frames.job_for(aid,jobs.connect);jobs.enqueue(job,'synthetic');record=jobs.claim()
    result=dict(status='Ready',retained=True,dimensions=[3508,2480],source_dimensions=[3508,2480],source_sha256='b'*64,sha256='a'*64,output={'sha256':'a'*64,'bytes':123},edition_number=27,edition_total=100)
    jobs.finish(job['id'],record['lease_token'],result=result)
    snapshot=frames.resolve(aid,jobs.connect)
    assert snapshot['mapping']==os_pages.prodigi_mapping_for_frame_size(color,'S')
    assert snapshot['mapping']['prodigi_code']=='GLOBAL-CFP-A4'
    assert snapshot['number']==27 and snapshot['identity']['line_id']=='gid://shopify/LineItem/555'
    monkeypatch.setattr(prep,'connect',jobs.connect)
    assert prep.resolve(aid)==snapshot
    from auto_editions_store import Preparations
    monkeypatch.setattr(runtime,'stores',lambda:(Preparations(jobs.connect),jobs))
    monkeypatch.setattr(runtime,'storage',lambda:'storage')
    assert runtime.job_for(aid)==(job,'storage')
    assert frames.identity_proof(snapshot)
    changed=deepcopy(snapshot);changed['rendered_number']=28
    assert not frames.identity_proof(changed)
