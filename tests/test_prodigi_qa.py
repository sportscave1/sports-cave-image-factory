from copy import deepcopy
import pytest
from prodigi_qa import evaluate, address_matches
from prodigi_preparation import digest
from tests.test_prodigi_preparation import snapshot, order


def case():
    snap=snapshot()
    recipient={'name':'Synthetic Test','address':{'line1':'1 Example Street','line2':'Unit 2',
        'townOrCity':'Sydney','stateOrCounty':'NSW','postalOrZipCode':'2000','countryCode':'AU'}}
    snap.update(recipient=deepcopy(recipient),certificate_url='https://fixture.invalid/cert.pdf')
    remote=order();remote.update(recipient=recipient,shippingMethod='Standard',issues=[],
        packingSlip={'url':snap['certificate_url'],'status':'ready'})
    item=remote['items'][0];item.update(sizing='fitPrintArea',
        assets=[{'printArea':'default','url':'https://fixture.invalid/pinned.jpg','status':'NotYetDownloaded'}])
    return snap,remote,item


def test_all_questions_have_independent_evidence_and_pending_download_is_truthful():
    snap,remote,item=case()
    qa=evaluate(snap,remote,item,digest(item['assets'][0]['url']))
    assert all(qa['checks'].values()) and not qa['blockers']
    assert qa['supplier_download_confirmed'] is False
    item['assets'][0]['status']='Complete'
    assert evaluate(snap,remote,item,digest(item['assets'][0]['url']))['supplier_download_confirmed'] is True


@pytest.mark.parametrize('change,field',[
    (lambda s,o,i:i.update(sku='WRONG'),'product_option'),
    (lambda s,o,i:i.update(attributes={'color':'white'}),'frame'),
    (lambda s,o,i:i['assets'][0].update(url='https://fixture.invalid/other.jpg'),'artwork_upload'),
    (lambda s,o,i:i['assets'][0].update(status='Error'),'artwork_upload'),
    (lambda s,o,i:s.update(rendered_number=13),'edition_number'),
    (lambda s,o,i:s.update(dimensions=[5940,4200]),'sent_to_production'),
    (lambda s,o,i:o['recipient']['address'].update(line2='Unit 3'),'shipping'),
    (lambda s,o,i:o.update(shippingMethod='Express'),'shipping'),
    (lambda s,o,i:s.update(certificate_url='https://fixture.invalid/wrong.pdf'),'certificate'),
    (lambda s,o,i:o['packingSlip'].update(status='error'),'packing_slip'),
    (lambda s,o,i:o.update(issues=[{'type':'fulfilment_issue'}]),'final_check'),
])
def test_each_missing_or_mismatched_question_blocks_ready(change,field):
    snap,remote,item=case();original=digest(item['assets'][0]['url']);change(snap,remote,item)
    qa=evaluate(snap,remote,item,original)
    assert not qa['checks'][field] and not qa['checks']['final_check'] and qa['blockers']


def test_incomplete_address_never_matches_and_state_aliases_are_explicit():
    assert not address_matches({}, {})
    snap,remote,_=case()
    snap['recipient']['state_aliases']=['NSW','New South Wales']
    remote['recipient']['address']['stateOrCounty']='New South Wales'
    assert address_matches(snap['recipient'],remote['recipient'])
    remote['recipient']['address']['postalOrZipCode']='02000'
    assert not address_matches(snap['recipient'],remote['recipient'])


def test_qa_result_contains_reasons_but_no_customer_address_or_signed_urls():
    snap,remote,item=case()
    result=str(evaluate(snap,remote,item,digest(item['assets'][0]['url'])))
    assert '1 Example Street' not in result and 'https://' not in result
