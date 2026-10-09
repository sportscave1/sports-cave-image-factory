"""Offline active-page fixture. No remote products, media, saves or Meta writes."""
from contextlib import ExitStack
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch

from PIL import Image
import streamlit as st
if os.environ.get('REFRESH_BASELINE_SOURCE') and not getattr(sys.modules.get('ads_page'),'_refresh_baseline_loaded',False):
    for name in ('ads_refresh_plan','ads_refresh_generation','ads_refresh_reference','ads_refresh_saved','meta_review_handoff','ads_page'):
        baseline = types.ModuleType(name)
        baseline.__file__ = str(Path(name+'.py').resolve())
        sys.modules[name] = baseline
        exec(compile((Path(os.environ['REFRESH_BASELINE_SOURCE'])/(name+'.py')).read_text(encoding='utf-8'), baseline.__file__, 'exec'), baseline.__dict__)
    baseline._refresh_baseline_loaded=True
import ads_page as ads
import ads_posting_handoff as posting
import ads_refresh_saved as saved
import meta_review_handoff as handoff
from tests.test_ads_refresh_plan import fixture, executions
from tests.test_ads_refresh_save_restore import RefreshSaveRestoreTests
from tests.test_ads_refresh_workflow import ROW
from tests.test_ads_posting_handoff import completed_ad


def ready_carousel(count=5):
    result = fixture()
    _, workflow = completed_ad('Carousel', 'creative_refresh')
    workflow['context_key'] = result['context_key']
    copy = workflow['ad_notes']['carousel']
    copy['primary_texts'] = ['A place for the rivalry.', 'Remember the roar of the stands.',
                            'Collect the moments you love.', 'Football belongs in your home.',
                            'Your story deserves a wall.']
    headlines = ['The Rivalry', 'Match Day', 'Collector Spirit', 'Your Football', 'Own a Memory']
    descriptions = ['Two greats', 'Recall the roar', 'A personal icon', 'Home advantage', 'Made to display']
    copy['headlines'] = headlines.copy()
    copy['descriptions'] = descriptions.copy()
    for i, card in enumerate(copy['cards']):
        card.update(headline=headlines[i], description=descriptions[i], destination_url=result['product_url'])
    workflow['ad_notes']['refresh_executions'] = executions(result)
    if count != 5:
        source = deepcopy(result['creative_refresh_context']['source_winner'])
        if count == 6:
            source['carousel_cards'].append(dict(position=6, image_url='https://example.fbcdn.net/card6.png', scene='study', role='collector ownership'))
            copy['cards'].append({**copy['cards'][-1], 'position':6, 'slot_id':'carousel-06', 'headline':'Football History', 'description':'The collector'})
            extra = deepcopy(workflow['slots']['carousel-05'])
            output = io.BytesIO(); Image.new('RGB', (1080,1080), 'purple').save(output, 'PNG')
            extra.update(data=output.getvalue(), source_hash='sixth-distinct', position=6, slot_id='carousel-06')
            workflow['slots']['carousel-06'] = extra
        else:
            source['carousel_cards'] = source['carousel_cards'][:count]
            copy['cards'] = copy['cards'][:count]
            workflow['slots'] = dict(list(workflow['slots'].items())[:count])
        result = ads.build_ads_result_record(result['product_name'], result['category'], result['country'], 'Carousel',
            product_id=result['product_id'], product_url=result['product_url'], variation_token='synthetic-v3',
            creative_refresh_context={**result['creative_refresh_context'], 'source_winner':source})
        workflow['context_key'] = result['context_key']
        # Six-card fixture is for UI/count checks; it deliberately has incomplete analysis.
    from tests.fixtures.carousel_evolution import attach_reviews
    workflow['ad_notes']['refresh_executions'] = attach_reviews(
        result,copy,workflow['ad_notes']['refresh_executions'][:count])
    ads._store_carousel_copy_notes(workflow, copy, result)
    return result, workflow


def main():
    st.set_page_config(layout='wide')
    kind = st.query_params.get('format', 'Instant Experience')
    count = int(st.query_params.get('count', '5'))
    if 'seeded' not in st.session_state:
        result, workflow = ready_carousel(count) if kind == 'Carousel' else RefreshSaveRestoreTests().ready_ie()
        for slot in workflow['slots'].values():
            slot.update(ads.ads_image_workflow.build_instant_experience_preview_thumbnail(slot['data']))
        if kind == 'Carousel':
            context = result['creative_refresh_context']
            for i,card in enumerate(context['source_winner']['carousel_cards'],1):
                card['image_sha256'] = f'fixture-card-{i}'
            result=ads.build_ads_result_record(result['product_name'],result['category'],result['country'],kind,
                product_id=result['product_id'],product_url=result['product_url'],variation_token='synthetic-v3',
                creative_refresh_context=context)
            workflow['context_key']=result['context_key']
        saved.restore(saved.dumps(result, workflow), st.session_state)
        st.session_state.seeded = True
    output = io.BytesIO(); Image.new('RGB',(640,640),'#876842').save(output,'PNG')
    def load_media(_digest):
        st.session_state['fixture_media_reads'] = st.session_state.get('fixture_media_reads',0)+1
        return output.getvalue(), 'image/png'
    def upload(_token, folder, items, **kwargs):
        results=[]
        for item in items:
            path=folder+'/'+item['relative_path']
            st.session_state.setdefault('fixture_saved_files',{})[path]=bytes(item['data'])
            results.append({'relative_path':item['relative_path'], 'metadata':{'id':'fixture:'+path,'rev':'fixture','path_display':path}})
        return {'successes':results,'failures':[]}
    with ExitStack() as stack:
        for owner, name, kwargs in (
            (ads,'load_edition_ops_product_rows',dict(return_value=[ROW])),
            (ads,'current_ads_user',dict(return_value={})),
            (ads,'record_activity_log',dict(return_value=None)),
            (ads,'record_ad_prompt_generated',dict(return_value=None)),
            (ads,'_save_ads_upload_metadata',dict(return_value=None)),
            (ads,'_ads_dropbox_connection',dict(return_value=('fixture','/approved'))),
            (ads,'_render_ads_folder_picker',dict(return_value='/approved')),
            (ads.os_accounts,'can_access_page',dict(return_value=True)),
            (handoff.store,'load_media',dict(side_effect=load_media)),
            (ads.dropbox_integration,'ensure_folder_path',dict(return_value=None)),
            (ads.dropbox_integration,'get_metadata_if_exists',dict(return_value={})),
            (ads.dropbox_integration,'upload_batch',dict(side_effect=upload)),
        ):
            stack.enter_context(patch.object(owner,name,**kwargs))
        stack.enter_context(patch('requests.sessions.Session.request',side_effect=AssertionError('No external network in fixture')))
        if st.session_state.get('current_page') == ads.POSTING_ROUTE:
            st.success('Posting handoff ready')
            st.caption(str(len(st.session_state[posting.PENDING_KEY]['package']['assets']))+' saved assets')
        else:
            ads.render_page('creative_refresh')


if __name__ == '__main__':
    main()
