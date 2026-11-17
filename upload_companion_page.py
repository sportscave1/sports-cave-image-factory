"""Administrator view for the local Edge Upload Companion."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def extension_package():
    source = Path(__file__).parent / 'windows-upload-companion'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for filename in ('manifest.json', 'os-bridge.js', 'worker.js', 'composer.js', 'staff-queue.js', 'design-queue.js'):
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
    percent = min(90, int(10 + elapsed / 20 * 80))
    return percent, f'About {int(elapsed)} min elapsed · time-based estimate, not measured completion'


def _jobs(jobs, *, designs, paused=False):
    import streamlit as st
    active_end = 3 if designs else 5
    active = [j for j in jobs if 1 <= j['stage'] <= active_end]
    waiting = [j for j in jobs if j['stage'] == 0]
    finished = [j for j in jobs if j['stage'] > active_end]
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
            if job.get('chat_url'):
                st.link_button('Open design chat ↗', job['chat_url'])
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
                           'Notes': j.get('detail', '')} for j in finished], hide_index=True, width='stretch')
        else:
            st.caption('No completed jobs yet.')


def render_page(user):
    import os_accounts
    import streamlit as st

    if not os_accounts.can_access_page(user, 'Upload Companion'):
        st.error('Companion Queues requires an authorised administrator.')
        return
    _markup('<style>' + (Path(__file__).parent / 'components' / 'companion_queues.css').read_text(encoding='utf8') + '</style>')
    with st.container(key='companion-dashboard'):
        _markup('<div class="cq-hero"><div><div class="cq-eyebrow">SPORTS CAVE / AUTOMATION</div>'
                '<h1>Companion control</h1><p>Your design and publishing workflows, in one place.</p></div>'
                '<div class="cq-capacity"><span>PARALLEL CAPACITY</span><strong>1 design <i>+</i> 1 upload</strong>'
                '<small>Independent queues · automatic progression</small></div></div>')
        designs, uploads = st.tabs(['Design queue', 'Upload queue'])
        with designs:
            render_design_queue()
        with uploads:
            render_queue()


def _connection(online):
    _markup(f'<div class="cq-connection"><span class="cq-dot {"green" if online else "amber"}"></span>'
            f'<b>{"Companion online" if online else "Waiting for companion"}</b>'
            '<span>Updates every 10 seconds</span></div>')


def render_queue():
    import streamlit as st
    from product_upload_staff_queue import list_jobs

    @st.fragment(run_every=10)
    def history():
        try:
            status = list_jobs()
        except Exception:
            st.warning('Could not load the upload queue. Retrying automatically.')
            return
        _connection(status['online'])
        _summary(status['jobs'], designs=False)
        _markup('<div class="cq-notice"><b>Add uploads from Design Studio</b><span>Press Publish now on each artwork. '
                'They wait here and run one at a time, continuing after success or failure.</span></div>')
        _jobs(status['jobs'], designs=False)
        st.caption('Showing the latest 20 upload jobs. Keep Edge open and the computer awake.')
    history()


def render_design_queue():
    import streamlit as st
    from morning_design_queue import settings, list_jobs
    from product_upload_staff_queue import list_jobs as upload_status

    @st.fragment(run_every=10)
    def history():
        try:
            control = settings()
            jobs = list_jobs()
            online = upload_status()['online']
        except Exception:
            st.warning('Could not load the design queue. Retrying automatically.')
            return
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
                        st.rerun()
                with pause:
                    if st.button('Pause', icon=':material/pause:', disabled=not enabled, key='cq-design-pause',
                                 help='Hold the next design. The current ChatGPT job keeps running.'):
                        settings(False)
                        st.rerun()
                _markup(f'<span class="cq-badge {"green" if enabled else "amber"}">{"Queue playing" if enabled else "Queue paused"}</span>')
        _jobs(jobs, designs=True, paused=not control['enabled'])
        st.caption('Up to 100 jobs · active jobs first · Edge must stay open and signed in; keep the computer awake.')
    history()
