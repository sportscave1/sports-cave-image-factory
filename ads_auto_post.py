"""Automatic Ads-only Dropbox destination and save-before-Posting orchestration."""
import hashlib
import uuid

SCROLL_KEY = 'ads-posting-scroll-top'


def destination(api, root, result):
    """Use the configured Files root and the same safe naming as other exports."""
    values = (result.get('category'), result.get('product_name'), result.get('country'),
              result.get('campaign_type'),
              'Creative Refresh' if result.get('workflow_mode') == 'creative_refresh' else 'New Ads')
    if not all(str(v or '').strip() for v in values):
        raise ValueError('Select the product, category, country and campaign type before posting.')
    path = api.normalize_dropbox_path(root.rstrip('/') + '/04_OUTPUT/ads')
    for value in values:
        name = api.sanitize_path_component(str(value), fallback='')
        if not name or not name.strip('. '):
            raise ValueError('The Ads destination contains an invalid name.')
        path = api.join_upload_path(path, name)
    if not api.path_is_within_root(path, root):
        raise ValueError('The Ads destination is outside the approved Files root.')
    return path


def save_and_queue(ads, result, workflow, user, progress_callback=None, *, navigate=True):
    """Keep existing export, receipt validation and refresh persistence intact."""
    if not ads.os_accounts.can_access_page(user, 'Files'):
        raise ValueError('Files access is not approved for this account.')
    token, root = ads._ads_dropbox_connection()
    parent = destination(ads.dropbox_integration, root, result)
    # One stable package per draft; retries reuse it, new drafts cannot overwrite it.
    binding = hashlib.sha256(parent.casefold().encode()).hexdigest()
    if workflow.get('auto_ads_destination_binding') != binding:
        workflow['auto_ads_package_id'] = uuid.uuid4().hex[:12]
        workflow['auto_ads_destination_binding'] = binding
        workflow['outcomes'] = {}
        workflow.pop(ads.posting_handoff.SAVED_PACKAGE_KEY, None)
    package_id = workflow.setdefault('auto_ads_package_id', uuid.uuid4().hex[:12])
    folder = ads.dropbox_integration.join_upload_path(parent,
        ads.build_ads_export_folder_name(result, workflow) + ' - ' + package_id)
    workflow['saved_folder_path'] = folder
    workflow['destination_path'] = parent
    previous = {key for key, row in (workflow.get('outcomes') or {}).items() if row.get('status') == 'saved'}
    outcomes = ads.save_ads_images_to_dropbox(token, root, parent, result, workflow,
                                            progress_callback=progress_callback)
    workflow['outcomes'] = outcomes
    ads._save_ads_upload_metadata({k:v for k,v in outcomes.items() if k not in previous}, user)
    ads._ads_clear_directory_cache(parent, folder)
    if any(row.get('status') == 'failed' for row in outcomes.values()):
        raise ValueError('Some files could not be saved. Retry Post now; Posting has not been opened.')
    package = workflow.get(ads.posting_handoff.SAVED_PACKAGE_KEY)
    if not package or package.get('source_signature') != ads._ads_saved_source_signature(result, workflow):
        raise ValueError(workflow.get('posting_package_error') or 'The complete saved package could not be verified. Retry Post now.')
    if result.get('workflow_mode') == ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH:
        if not workflow.get('refresh_workspace_saved'):
            raise ValueError('The refreshed workspace could not be saved. Retry Post now.')
        import ads_refresh_saved
        _, saved = ads_refresh_saved.loads(workflow['refresh_workspace_export'])
        package = saved[ads.posting_handoff.SAVED_PACKAGE_KEY]
        ads.st.query_params['refresh_saved_folder'] = folder
        ads.st.query_params.pop('handoff_id', None)
    ads.record_activity_log('ad_images_saved', 'Ads', f"Saved ad package: {result['product_name']}",
                            entity_type='dropbox_folder', entity_id=folder,
                            metadata={'campaign_type': result['campaign_type'], 'destination': folder})
    ads.posting_handoff.queue_saved_package(package, state=ads.st.session_state)
    if navigate:
        ads.st.session_state[SCROLL_KEY] = uuid.uuid4().hex
        ads.st.session_state['current_page'] = ads.POSTING_ROUTE
        ads.st.session_state['selected_page'] = ads.POSTING_ROUTE
        ads.st.session_state['current_page_source'] = 'ads-saved-package'
        ads.st.query_params['page'] = ads.POSTING_PAGE_KEY
    return package



def render(ads, result, workflow, *, source_matches=True, quality_issues=None):
    st = ads.st
    issues = list(quality_issues or [])
    refresh = result.get('workflow_mode') == ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
    if not source_matches:
        issues.append('Settings changed. Submit them before continuing.')
    if refresh:
        issues += ads._creative_refresh_asset_issues(result, workflow)
        issues += ads._creative_refresh_visual_review_issues(result, workflow)
        plan = (result.get('creative_refresh_context') or {}).get('refresh_plan')
        if (ads.ads_refresh_generation.plan.preserve.active(plan) or ads.ads_refresh_generation.plan.distinct.active(plan)) and ads._ads_image_valid_slots(result, workflow):
            issues += ads.creative_refresh_quality_issues(result, workflow)
    elif ads._is_instant_experience_result(result):
        if not ads.instant_experience_package_ready(result, workflow):
            issues.append('Complete all three images and their copy before continuing.')
    elif not ads.ads_images_ready(result, workflow):
        issues.append('Complete the images before continuing.')
    if ads.google_ads.platform_for(result) != 'meta':
        issues.append(ads.google_ads.POSTING_HELP)
    import ads_direct_post as direct
    settings, targeting_issues = direct.render_settings(result, workflow)
    issues += targeting_issues
    if not ads.os_accounts.can_access_page(ads.current_ads_user(), 'Posting'):
        issues.append('Posting access is required to submit ads.')
    if workflow.get('direct_post_submission_id'):
        issues.append('This package has been submitted. Check its posting notification or open Posting for recovery.')
    elif st.session_state.get('posting_tracked_job') or st.query_params.get('meta_posting_job'):
        issues.append('Finish or review the current posting job before submitting another package.')
    if issues:
        st.caption(' · '.join(dict.fromkeys(issues)))
    clicked = st.button('Post now', type='primary', use_container_width=True,
                        disabled=bool(issues) or bool(workflow.get('saving')),
                        key=f"ads-post-now::{result['context_key']}")
    if not clicked:
        return
    workflow['saving'] = True
    st.session_state[ads._ads_image_state_key()] = workflow
    progress = st.progress(0, text='Saving ad package…')
    def update(index, total, label, uploaded, size):
        fraction = min(1, uploaded / size) if size else 1
        progress.progress(min(1.0, ((index - 1) + fraction) / max(total, 1)), text=f'Saving {label}')
    opened = False
    try:
        package = save_and_queue(ads, result, workflow, ads.current_ads_user(), update, navigate=False)
        progress.progress(1.0, text='Saved. Starting Meta posting…')
        direct.submit_saved(package, settings, workflow)
        opened = True
    except Exception as error:
        ads.logging.warning('Automatic Ads save/handoff failed: %s', error)
        st.error(str(error))
        st.caption('Your saved package and Posting draft are retained. Open Posting to review or recover this job.')
    finally:
        workflow['saving'] = False
        st.session_state[ads._ads_image_state_key()] = workflow
        progress.empty()
    if opened:
        st.rerun()


def scroll_to_top(st):
    token = st.session_state.pop(SCROLL_KEY, None)
    if not token:
        return
    # The Streamlit main section scrolls independently of window in some versions.
    st.components.v1.html('''<script>
    const reset = () => {
      const w = window.parent;
      w.scrollTo({top: 0, left: 0, behavior: 'instant'});
      w.document.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main')
        .forEach(el => el.scrollTo({top: 0, left: 0, behavior: 'instant'}));
    };
    requestAnimationFrame(reset); setTimeout(reset, 150); setTimeout(reset, 450);
    </script>''' + '<!--' + token + '-->', height=0)
