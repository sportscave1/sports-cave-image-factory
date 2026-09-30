"""Ads UI/storage cleanup tests; no remote storage or Meta mutations."""
import copy
import hashlib
import json
from pathlib import PurePosixPath
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import ads_page as ads
import ads_google_demand_gen as google
import ads_creative_refresh as refresh
import ads_package_paths as paths
from ads_creation_ui import creation_instructions
from ads_meta_contract import META_AD_URL_PARAMETERS
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_ads_refresh_workflow import completed_single
from tests.test_ads_google_demand_gen import MemoryDropbox, completed_csv, image_bytes


class AdsCleanupTests(unittest.TestCase):
    def test_creation_instructions_hide_tracking_for_all_formats_and_saved_prompts(self):
        for campaign in ('Single Image / Video', 'Carousel', 'Instant Experience'):
            for category in ('Football', 'Baseball', 'Motorsport'):
                with self.subTest(campaign=campaign, category=category):
                    prompt = ads.build_ads_prompt('Collector Legacy', category, 'Australia', campaign,
                        product_url='https://sportscave.com.au/products/collector')
                    before = prompt
                    display = creation_instructions(prompt)
                    self.assertNotIn(META_AD_URL_PARAMETERS, display)
                    self.assertNotIn('URL parameters', display)
                    self.assertNotIn('META URL PARAMETERS', display)
                    self.assertEqual(prompt, before)
                    self.assertIn('Collector Legacy', display)
                    # The clipboard component is the shared new/saved prompt boundary.
                    with patch.object(ads, '_PROMPT_COPY_COMPONENT') as component:
                        ads.render_prompt_copy_button(prompt, 'test', track_copy=True)
                    self.assertEqual(component.call_args.kwargs['prompt_text'], display)
        sample = 'Winner copy and URL https://sportscave.com.au/products/collector'
        self.assertEqual(creation_instructions(sample), sample)

    def test_all_meta_result_ui_branches_have_no_url_parameters_section(self):
        for campaign in ('Single Image / Video', 'Carousel', 'Instant Experience'):
            for mode in ('new', 'creative_refresh'):
                code = '''
import ads_page as ads
from unittest.mock import patch
result = ads.build_ads_result_record('Collector Legacy','Football','Australia',CAMPAIGN,
    product_url='https://sportscave.com.au/products/collector',
    creative_refresh_context=CONTEXT)
with patch.object(ads, '_ads_image_workflow', return_value={}), \
     patch.object(ads, '_render_instant_experience_concepts'), \
     patch.object(ads, '_render_ads_image_slots'), \
     patch.object(ads, '_render_ads_setup_notes'), \
     patch.object(ads, '_render_ads_image_save'), \
     patch.object(ads, '_render_saved_ad_post_now'), \
     patch.object(ads.ads_standard_workflow, 'render'):
    ads.render_supported_result(result)
'''.replace('CAMPAIGN', repr(campaign)).replace('CONTEXT', repr({'winning_primary_text':'Reference copy','winning_headline':'Collector'} if mode == 'creative_refresh' else None))
                with self.subTest(campaign=campaign, mode=mode):
                    app = AppTest.from_string(code).run(timeout=15)
                    self.assertFalse(app.exception)
                    visible = '\n'.join(str(e.value) for group in (app.subheader, app.caption, app.code, app.markdown) for e in group)
                    self.assertNotIn('URL parameters', visible)
                    self.assertNotIn('Paste this into', visible)
                    self.assertNotIn(META_AD_URL_PARAMETERS, visible)

    def test_meta_packages_and_resaves_are_flat_with_unchanged_names_and_handoff(self):
        for campaign in ('Single Image / Video', 'Carousel', 'Instant Experience'):
            for mode in ('new', 'creative_refresh'):
                with self.subTest(campaign=campaign, mode=mode):
                    result, workflow = completed_single() if campaign == 'Single Image / Video' else completed_ad(campaign, mode)
                    result['workflow_mode'] = mode
                    expected_names = {ads._meta_output_filename(result, workflow, slot)
                                      for slot in ads.ads_image_workflow.campaign_image_slots(campaign)}
                    files = save_locally(result, workflow)
                    folder = workflow['saved_folder_path']
                    self.assertEqual({str(PurePosixPath(p).parent) for p in files}, {folder})
                    self.assertTrue(expected_names.issubset({PurePosixPath(p).name for p in files}))
                    self.assertTrue(any(p.endswith('.csv') for p in files))
                    self.assertTrue(any(p.endswith('.txt') for p in files))
                    package = workflow[ads.posting_handoff.SAVED_PACKAGE_KEY]
                    for asset in package['assets']:
                        self.assertEqual(files[asset['path']], asset['data'])
                        self.assertEqual(str(PurePosixPath(asset['path']).parent), folder)
                    csv_file = next(f for f in package['files'] if f['filename'].endswith('.csv'))
                    self.assertEqual(files[csv_file['path']], package['copy_csv'])
                    self.assertEqual(ads._ads_export_folder_path(folder, result, workflow), folder)
                    self.assertEqual(ads._ads_export_folder_path('/approved', result, workflow), folder)
                    files.update(save_locally(result, workflow))
                    self.assertEqual(workflow['saved_folder_path'], folder)
                    self.assertEqual({str(PurePosixPath(p).parent) for p in files}, {folder})
                    self.assertEqual(len(workflow[ads.posting_handoff.SAVED_PACKAGE_KEY]['assets']), 5 if campaign == 'Carousel' else 3)

    def test_explicit_meta_resave_copies_legacy_nested_images_to_root(self):
        result, workflow = completed_ad('Carousel')
        files = save_locally(result, workflow)
        folder = workflow['saved_folder_path']
        historical = {}
        for spec in ads.ads_image_workflow.campaign_image_slots('Carousel'):
            receipt = workflow['outcomes'][spec['id']]
            old_path = receipt['path']
            receipt['path'] = folder + '/images/' + receipt['filename']
            historical[receipt['path']] = files[old_path]
        self.assertFalse(paths.saved_files_are_flat(workflow))
        # Old packages still validate; only a deliberate re-save writes flat files.
        package = workflow[ads.posting_handoff.SAVED_PACKAGE_KEY]
        for asset in package['assets']:
            asset['path'] = folder + '/images/' + asset['filename']
        package['package_hash'] = ads.posting_handoff.content_hash({k:v for k,v in package.items() if k!='package_hash'})
        ads.posting_handoff.validate_saved_package(package)
        rewritten = save_locally(result, workflow)
        self.assertEqual(sum(p.endswith('.jpg') for p in rewritten), 5)
        self.assertTrue(all(str(PurePosixPath(p).parent)==folder for p in rewritten))
        self.assertTrue(paths.saved_files_are_flat(workflow))
        self.assertFalse(set(historical) & set(rewritten))

    def test_flat_items_keep_existing_names_and_qualify_copy_collisions(self):
        items = paths.flat_items([{'relative_path':'images/existing-card-01.jpg','data':b'image'},
                                 {'relative_path':'route-one/headline.txt','data':b'one'},
                                 {'relative_path':'route-two/headline.txt','data':b'two'},
                                 {'relative_path':'csv/Carousel Copy.csv','data':b'csv'}])
        self.assertEqual([i['relative_path'] for i in items],
            ['existing-card-01.jpg','route-one--headline.txt','route-two--headline.txt','Carousel Copy.csv'])
        self.assertEqual([i['data'] for i in items], [b'image',b'one',b'two',b'csv'])
        with self.assertRaisesRegex(ValueError, 'collision'):
            paths.flat_items([{'relative_path':'same.jpg'},{'relative_path':'same.jpg'}])

    def test_legacy_refresh_resave_uses_same_campaign_root(self):
        storage=MemoryDropbox()
        result={'package_name':'Existing Campaign'}
        items=[{'relative_path':'prompt.txt','data':b'prompt','size':6}]
        with patch.object(refresh.dropbox_integration,'upload_batch',side_effect=storage.upload), \
             patch.object(refresh.dropbox_integration,'ensure_folder_path') as mkdir, \
             patch.object(refresh.dropbox_integration,'get_metadata_if_exists',return_value=None):
            first=refresh.save_creative_refresh_package_to_dropbox('token','/Team','/Team/Ads',result,items)
            second=refresh.save_creative_refresh_package_to_dropbox('token','/Team',first['path'],result,items,saved_folder=first['path'])
        self.assertEqual(first['path'],second['path'])
        self.assertEqual(set(storage.files), {'/Team/Ads/Existing Campaign/prompt.txt'})
        self.assertTrue(all(c.args[1]==first['path'] for c in mkdir.call_args_list))

    def test_google_flat_save_old_nested_read_and_failed_resave_rollback(self):
        storage=MemoryDropbox()
        with patch.object(google.dropbox,'upload_batch',side_effect=storage.upload), \
             patch.object(google.dropbox,'get_file_bytes',side_effect=storage.read), \
             patch.object(google.dropbox,'ensure_folder_path') as mkdir:
            result, workflow=google.import_csv(completed_csv())
            for spec in google.IMAGE_SLOTS:
                workflow['slots'][spec['id']]=google.process_image(image_bytes(spec),spec)
            google.save_campaign('token','/Team','/Team/Ads',result,workflow)
            folder=workflow['saved_folder_path']
            manifest=workflow['outcomes']['_campaign']['path']
            self.assertEqual({str(PurePosixPath(p).parent) for p in storage.files},{folder})
            self.assertTrue(all(f"{folder}/{s['filename']}" in storage.files for s in google.IMAGE_SLOTS))
            committed=copy.deepcopy(storage.files)
            # Changed pixels plus a failed final manifest must leave the last save readable.
            workflow['slots'][google.IMAGE_SLOTS[0]['id']]=google.process_image(image_bytes(google.IMAGE_SLOTS[0],transparent=True),google.IMAGE_SLOTS[0])
            storage.fail=google.MANIFEST_FILENAME
            with self.assertRaises(google.GoogleCampaignError):
                google.save_campaign('token','/Team',folder,result,workflow)
            self.assertEqual(storage.files,committed)
            storage.fail=''
            google.load_campaign('token','/Team',manifest)
            # Simulate a genuine historical manifest with nested hash-addressed assets.
            old=json.loads(storage.files[manifest])
            for spec in google.IMAGE_SLOTS:
                slot=old['google_config']['image_slots'][spec['id']]
                nested=f"{folder}/assets/{slot['sha256']}/{spec['filename']}"
                storage.files[nested]=storage.files[slot['saved_path']]
                slot['saved_path']=nested
            storage.files[manifest]=json.dumps(old).encode()
            historical={p:b for p,b in storage.files.items() if '/assets/' in p}
            reopened, rework=google.load_campaign('token','/Team',manifest)
            self.assertEqual(google.asset_count(rework),9)
            google.save_campaign('token','/Team',folder,reopened,rework)
            self.assertEqual(rework['saved_folder_path'],folder)
            self.assertEqual({p:b for p,b in storage.files.items() if '/assets/' in p},historical)
            self.assertTrue(all(str(PurePosixPath(v['path']).parent)==folder for v in rework['outcomes'].values()))
            self.assertTrue(all(c.args[1]==folder for c in mkdir.call_args_list))


if __name__=='__main__':
    unittest.main()
