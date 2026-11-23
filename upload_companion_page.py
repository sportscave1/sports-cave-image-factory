"""Administrator view for the local Edge Upload Companion."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from companion_display import read as read_display, invalidate as invalidate_display, page_rows, visible


def extension_package():
    source = Path(__file__).parent / 'windows-upload-companion'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for filename in ('manifest.json', 'message-deadline.js', 'os-bridge.js', 'queue-wake.js', 'worker.js', 'composer.js', 'staff-queue.js', 'design-queue.js', 'ad-queue.js', 'ad-artifacts.js', 'ad-downloads.js', 'ad-library.js', 'ad-repair.js', 'orders-queue.js', 'orders-progress.js', 'orders-wake.js', 'prodigi-browser.js', 'prodigi-wait.js', 'prodigi-page.js', 'prodigi-dashboard-qa.js', 'prodigi-signin.js', 'prodigi-signin-page.js', 'inbox-queue.js', 'inbox-page.js'):
            bundle.write(source / filename, filename)
    return archive.getvalue()


def _html(value):
    from html import escape
    return escape(str(value or ''))


def _markup(value):
    import streamlit as st
    st.markdown(value, unsafe_allow_html=True)


def _summary(jobs, *, designs, paused=False):
    active = sum(1 <= j['stage'] <= (3 if designs else 5) for j in jobs)
    waiting = sum(j['stage'] == 0 for j in jobs)
    saved = sum(bool(j.get('file_path')) if designs else j['stage'] == 6 for j in jobs)
    attention = sum(j['stage'] == (5 if designs else 7) and not j.get('file_path') for j in jobs)
    cards = [('Running', active, 'One active job', 'blue'),
             ('Waiting', waiting, 'Paused · press Play' if paused else 'Starts automatically', 'gold'),
             ('Completed' if designs else 'Published', saved, 'Verified output', 'green'),
             ('Needs attention', attention, 'Does not block the queue', 'amber')]
    import streamlit as st
    st.caption('Counts reflect the loaded queue window.')
    _markup('<div class="cq-metrics">' + ''.join(
        f'<div class="cq-metric {tone}"><span>{label}</span><strong>{number:02d}</strong><small>{hint}</small></div>'
        for label, number, hint, tone in cards) + '</div>')


def estimated_progress(job):
    """Stage/time estimate only; never represents verified artwork completion."""
    from datetime import datetime, timezone
    stage = job['stage']
    if stage == 1:
        return 5, 'Opening ChatGPT'
    if stage == 3:
        return 95, 'PSD uploaded · verifying handoff'
    try:
        elapsed = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(job['updated_at'])).total_seconds() / 60)
    except (KeyError, ValueError, TypeError):
        return 10, 'Generating · completion time varies'
    percent = 10  # Generation has no measurable completion percentage.
    return percent, f'{int(elapsed)} min elapsed · waiting for verified output'


def _jobs(jobs, *, designs, paused=False, user=None):
    import streamlit as st
    active_end = 3 if designs else 5
    active = [j for j in jobs if 1 <= j['stage'] <= active_end]
    waiting = [j for j in jobs if j['stage'] == 0]
    finished = [j for j in jobs if j['stage'] > active_end]
    if not designs:
        failed = [j for j in finished if j['stage'] == 7]
        if failed:
            _markup('<div class="cq-section"><h3>Needs attention</h3></div>')
        for job in failed:
            with st.container(border=True):
                text, action = st.columns([12, 1])
                with text:
                    _markup(f'<div class="cq-job"><h4>{_html(job["title"])}</h4></div>')
                    st.caption(job.get('detail') or job['label'])
                with action:
                    if st.button('', icon=':material/restart_alt:', key='cq-upload-reset-'+job['id'],
                                 help='Restart from the original PSD and regenerate mockups', disabled=user is None):
                        from product_upload_staff_queue import restart
                        try:
                            restart(job['id'], user, job['updated_at'])
                            invalidate_display()
                            st.rerun()
                        except (ValueError, PermissionError) as error:
                            st.error(str(error))
        finished = [j for j in finished if j['stage'] != 7]
    _markup('<div class="cq-section"><h3>Running now</h3></div>')
    if not active:
        message = ('Queue paused. Press Play to start the next job.' if paused else
                   'No job running. The companion starts automatically when work is available.')
        _markup(f'<div class="cq-empty">{message}</div>')
    for job in active:
        with st.container(border=True):
            _markup(f'<div class="cq-job"><h4>{_html(job["title"])}</h4><span class="cq-badge blue">{_html(job["label"])}</span></div>')
            percent, text = estimated_progress(job) if designs else (job['percent'], job['label'])
            st.progress(percent / 100, text=f'{"Estimated " if designs else "Stage progress "}{percent}% · {text}')
            if job.get('updated_at'):
                st.caption('Latest checkpoint: ' + str(job['updated_at']))
            if job.get('detail'):
                st.caption(job['detail'])
            if job.get('chat_url'):
                st.link_button('Open design chat ↗', job['chat_url'])
            if designs:
                for action, label in (('defer', 'Move to pending'), ('cancel', 'Cancel design')):
                    if job.get('can_'+action) and st.button(label, key='cq-design-'+action+'-'+job['id'], disabled=user is None):
                        from morning_design_queue import control
                        try:
                            control(job['id'], user, job['updated_at'], action)
                            invalidate_display();st.rerun()
                        except (ValueError, PermissionError) as error:
                            st.error(str(error))
    _markup(f'<div class="cq-section"><h3>Waiting queue</h3><span>{len(waiting)}</span></div>')
    if waiting:
        st.dataframe([{'Position': n, 'Design' if designs else 'Artwork': j['title'], 'Status': 'Waiting'}
                      for n, j in enumerate(waiting, 1)], hide_index=True, width='stretch')
    else:
        _markup('<div class="cq-empty">Nothing waiting. Completed designs are in history below.</div>')
    with st.expander(f'Completed & stopped history · {len(finished)}', expanded=False):
        if finished:
            st.dataframe([{'Design' if designs else 'Artwork': j['title'], 'Status': j['label'],
                           'Saved file' if designs else 'Live listing': j.get('file_path') if designs else j.get('storefront'),
                           'Last update': j.get('updated_at'), 'Notes': j.get('detail', '')} for j in page_rows(finished, 'cq-design-history-page' if designs else 'cq-upload-history-page')], hide_index=True, width='stretch')
        else:
            st.caption('No completed jobs yet.')


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.can_access_page(user, 'Upload Companion'):
        st.error('Companion Queues requires an authorised administrator.')
        return
    from workspace_display_cache import user_scope
    st.session_state['companion-display-scope'] = user_scope(user)
    st.session_state['companion-visible-now'] = visible()
    _markup('<style>' + (Path(__file__).parent / 'components' / 'companion_queues.css').read_text(encoding='utf8') + '</style>')
    with st.container(key='companion-dashboard'):
        _markup('<div class="cq-hero"><div><div class="cq-eyebrow">SPORTS CAVE / AUTOMATION</div>'
                '<h1>Companion control</h1><p>Designs, product uploads, Meta ads, order preparation and SEO audits.</p></div>'
                '<div class="cq-capacity"><span>PARALLEL CAPACITY</span><strong>1 design <i>+</i> 1 upload <i>+</i> 1 ad <i>+</i> 1 order</strong>'
                '<small>Independent queues · automatic progression</small></div></div>')
        with st.expander('This browser · companion version'):
            from product_upload_gallery import render as render_browser_connection
            render_browser_connection(key='companion-browser-connection', mode='companion-health')
        with st.expander('Inbox Companion'):
            from inbox_companion_ui import controls as inbox_controls
            inbox_controls(user)
        designs, uploads, ads, orders, seo = st.tabs(['Design queue', 'Upload queue', 'Ads queue', 'Orders queue', 'SEO queue'],
                                        key='companion-queue-tabs', on_change='rerun')
        if designs.open:
            with designs:
                render_design_queue(user)
        if uploads.open:
            with uploads:
                render_queue(user)
        if ads.open:
            with ads:
                render_ad_queue()
        if orders.open:
            with orders:
                from prodigi_preparation_ui import dashboard
                dashboard()
        if seo.open:
            with seo:
                from seo_companion_ui import controls
                controls(user)


def _connection(online, *, name='Companion'):
    _markup(f'<div class="cq-connection"><span class="cq-dot {"green" if online else "amber"}"></span>'
            f'<b>{name + " online" if online else "Waiting for " + name.lower()}</b>'
            '<span>Refreshes automatically</span></div>')


def render_queue(user=None):
    import streamlit as st
    from product_upload_staff_queue import list_jobs, settings

    @st.fragment(run_every=2 if st.session_state.get('companion-visible-now', True) else None)
    def history():
        def load():
            return dict(status=list_jobs(display_only=True), control=settings())
        value = read_display('Upload queue', load)
        if value is None: return
        status, control = value['status'], value['control']
        _connection(status['online'])
        _summary(status['jobs'], designs=False, paused=not control['enabled'])
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                _markup('<div class="cq-eyebrow">UPLOAD QUEUE</div><h3 class="cq-control-title">Control the next upload.</h3>')
                st.caption('Pause holds the next upload. The current upload and its ChatGPT work continue until finished.')
            with right:
                enabled = control['enabled']
                play, pause = st.columns(2)
                with play:
                    if st.button('Play', icon=':material/play_arrow:', disabled=enabled, key='cq-upload-play',
                                 help='Resume starting queued uploads. Current work is never restarted.'):
                        settings(True)
                        invalidate_display()
                        st.rerun()
                with pause:
                    if st.button('Pause', icon=':material/pause:', disabled=not enabled, key='cq-upload-pause',
                                 help='Hold the next upload. The current upload keeps running.'):
                        settings(False)
                        invalidate_display()
                        st.rerun()
                _markup(f'<span class="cq-badge {"green" if enabled else "amber"}">{"Queue playing" if enabled else "Queue paused"}</span>')
        _markup('<div class="cq-notice"><b>Add uploads from Design Studio</b><span>Press Add to queue on each artwork. '
                'They wait here and run one at a time while the queue is playing.</span></div>')
        _jobs(status['jobs'], designs=False, paused=not control['enabled'], user=user)
        st.caption('Showing the latest 20 upload jobs. Keep Edge open and the computer awake.')
    history()


def render_design_queue(user=None):
    import streamlit as st
    from morning_design_queue import settings, list_jobs
    from product_upload_staff_queue import desktop_online

    @st.fragment(run_every=2 if st.session_state.get('companion-visible-now', True) else None)
    def history():
        def load():
            return dict(control=settings(), jobs=list_jobs(display_only=True), online=desktop_online())
        value = read_display('Design queue', load)
        if value is None: return
        control, jobs, online = value['control'], value['jobs'], value['online']
        _connection(online)
        _summary(jobs, designs=True, paused=not control['enabled'])
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                _markup('<div class="cq-eyebrow">MORNING AUTOMATION</div><h3 class="cq-control-title">New ideas. Automatically in motion.</h3>')
                st.caption('New morning suggestions join the queue automatically. Pausing stops new starts; running jobs continue.')
            with right:
                enabled = control['enabled']
                play, pause = st.columns(2)
                with play:
                    if st.button('Play', icon=':material/play_arrow:', disabled=enabled, key='cq-design-play',
                                 help='Resume starting queued designs. Current work is never restarted.'):
                        settings(True)
                        invalidate_display()
                        st.rerun()
                with pause:
                    if st.button('Pause', icon=':material/pause:', disabled=not enabled, key='cq-design-pause',
                                 help='Hold the next design. The current ChatGPT job keeps running.'):
                        settings(False)
                        invalidate_display()
                        st.rerun()
                _markup(f'<span class="cq-badge {"green" if enabled else "amber"}">{"Queue playing" if enabled else "Queue paused"}</span>')
        _jobs(jobs, designs=True, paused=not control['enabled'], user=user)
        st.caption('Up to 100 jobs · active jobs first · Edge must stay open and signed in; keep the computer awake.')
    history()



def render_ad_queue():
    import streamlit as st
    from urllib.parse import urlencode
    from design_publish_ad import dashboard, settings
    from ads_companion_quick_add import render as quick_add
    quick_add()

    def links(job):
        if job.get('updated_at'):
            st.caption('Latest checkpoint: ' + str(job['updated_at']))
        if job.get('id'):
            import os_accounts
            st.link_button('View imported ad draft', '/?'+urlencode(dict(page=os_accounts.page_key_for_route('Ads'),ads_queue_job=job['id'])))
        if job.get('chat_url'):
            st.link_button('Open ad chat', job['chat_url'])
        if job.get('posting_id'):
            st.link_button('See in Posting', '/?' + urlencode(
                dict(page='ads_posting', meta_posting_job=job['posting_id'])))
        if job.get('targeting'):
            st.caption('Product set: ' + job['targeting']['product_set_name'] + ' · Audience: ' + job['targeting']['audience_name'])
        if not job.get('id'): return
        from ads_companion_controls import action
        from ads_page import current_ads_user
        for column,operation,label,allowed in zip(st.columns(3),('play','cancel','delete'),
                ('▶ Play / resume','■ Cancel','🗑 Delete'),(job.get('can_play'),job.get('can_cancel'),True)):
            if column.button(label,key='cq-ad-'+operation+'-'+job['id'],disabled=not allowed):
                try:
                    action(current_ads_user(),job['id'],operation)
                    invalidate_display()
                    st.rerun()
                except (ValueError,PermissionError) as error:st.error(str(error))

    @st.fragment(run_every=2 if st.session_state.get('companion-visible-now', True) else None)
    def history():
        status = read_display('Ads queue', dashboard)
        if status is None: return
        _connection(status['online'], name='Ads Companion')
        enabled = status['enabled']
        jobs = status['jobs']
        waiting = [job for job in jobs if job['stage'] == 'waiting']
        running = [job for job in jobs if job['active'] and job['stage'] != 'waiting']
        finished = [job for job in jobs if not job['active']]
        for column, label, count in zip(st.columns(4),
                ('Running', 'Waiting', 'Completed', 'Needs attention'),
                (len(running), len(waiting), sum(job['stage'] == 'complete' for job in finished),
                 sum(job['stage'] == 'failed' for job in finished))):
            column.metric(label, count)

        with st.container(border=True):
            controls, play, pause = st.columns([4, 1, 1], vertical_alignment='center')
            controls.subheader('Queue playing' if enabled else 'Queue paused')
            controls.caption('Pause holds the next ad. Running ads and product uploads continue.')
            if play.button('Play', icon=':material/play_arrow:', disabled=enabled, key='cq-ads-play'):
                settings(True)
                invalidate_display()
                st.rerun()
            if pause.button('Pause', icon=':material/pause:', disabled=not enabled, key='cq-ads-pause'):
                settings(False)
                invalidate_display()
                st.rerun()

        st.caption('Add products above or use Publish + ad in Design Studio. Cancel stops future automation; Delete hides the job without removing files or Meta receipts.')
        st.subheader('Running now')
        if not running:
            st.caption('No ad running.')
        for job in running:
            with st.container(border=True):
                st.write(job['title'])
                st.caption(f"{job['country']} | {job['sport']} | {job['label']}")
                if job.get('detail'):
                    st.caption(job['detail'])
                links(job)

        st.subheader('Waiting queue')
        if waiting:
            for position,job in enumerate(page_rows(waiting, 'cq-ads-waiting-page'),1):
                with st.container(border=True):
                    st.write(f"{position}. {job['title']}")
                    st.caption(f"{job['country']} · {job['sport']}")
                    links(job)
        else:
            st.caption('Nothing waiting.')

        with st.expander(f'Completed & stopped history ({len(finished)})'):
            if not finished:
                st.caption('No completed jobs yet.')
            for job in page_rows(finished, 'cq-ads-history-page'):
                st.write(job['title'])
                st.caption(f"{job['country']} | {job['sport']} | {job['label']}")
                if job['detail']:
                    st.caption(job['detail'])
                links(job)
        st.caption('Latest 100 ads. Keep Edge open and signed in with Companion 1.5.1 or later. Ad tabs work in the background; the computer must remain awake.')
    history()
