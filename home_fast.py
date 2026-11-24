"""Home panels consume bounded display snapshots, independent of shell rendering."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
from time import monotonic
from display_snapshot import Snapshots
from workspace_display_cache import user_scope
import os_accounts


# Separate from companion reads: saturated companion lanes cannot queue Home work.
SNAPSHOTS = Snapshots(workers=3, limit=32, byte_limit=32_000_000)


def sports_data(today):
    import home_sports_morning_brief as brief
    from morning_design_queue import list_jobs
    saved = brief.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False)
    edition = brief.parse_edition(brief._edition_json(saved), today) if saved else None
    # Optional archive/status failures must not take down today's published brief.
    try:
        editions, _ = brief.archive_page(today, size=20)
        # Home calendars need ranking metadata, not twenty full archived articles.
        editions = [dict(date=entry['date'], recommendations=[
            dict(sport=item['sport'], markets=item['markets'])
            for item in entry['recommendations']]) for entry in editions]
    except Exception:
        editions = []
    try:
        statuses = {job['id']: job['label'] for job in list_jobs(edition['date'], display_only=True)} if edition else {}
    except Exception:
        statuses = None
    return dict(saved=saved, editions=editions, statuses=statuses)


def meta_data(today):
    import home_meta_morning_brief as brief
    saved = brief.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False)
    try:
        refresh = brief.home_design_refresh.render_html(today)
    except Exception:
        refresh = ''
    import home_crm_reporting as crm
    from datetime import timedelta
    day = today - timedelta(days=1)
    try:
        cached_crm = dict(state='saved', data=crm.saved(day, day))
    except Exception:
        cached_crm = None
    import home_seo_report
    try:
        seo_report = home_seo_report.latest()
    except Exception:
        seo_report = {}
    return dict(saved=saved, refresh=refresh, crm=cached_crm, seo=seo_report)


def panel(st, user, today, name, loader, renderer):
    key = (user_scope(user), str(today), name)
    scope = user_scope(user)
    def current():
        # Session-state access also yields to pending navigation/stop requests.
        return (st.session_state.get('current_page', 'Dashboard') == 'Dashboard'
                and st.session_state.get('sports_cave_authenticated', True) is not False
                and user_scope(st.session_state.get('sports_cave_current_user') or {}) == scope)

    @st.fragment(run_every=30, parallel=True)
    def content():
        if not current():
            return
        # A separate status slot keeps loaded content at a stable position.
        # All widgets render once, directly in their owning fragment.
        status = st.empty()
        result = SNAPSHOTS.read(key, loader)
        if result['value'] is None and result['state'] == 'loading':
            status.caption(name + ' · loading saved information…')
            deadline = monotonic() + 8
            while result['value'] is None and result['state'] == 'loading' and monotonic() < deadline:
                SNAPSHOTS.wait(key, .05)
                if not current():
                    return
                result = SNAPSHOTS.read(key, loader)
        if not current():
            return
        value = result['value']
        if value is None:
            status.caption(name + (' · temporarily unavailable; retry below' if result['state'] == 'unavailable'
                                   else ' · loading saved information…'))
            if st.button('Retry ' + name, key='home-panel-retry-' + name):
                SNAPSHOTS.invalidate(key)
                st.rerun(scope='fragment')
            return
        status.empty()
        if result['state'] == 'stale':
            stamp = datetime.fromtimestamp(result['checked_at'], ZoneInfo('Australia/Sydney')).strftime('%H:%M')
            st.caption(f'Showing saved information checked at {stamp} Sydney · refreshing')
        renderer(value)
    content()


def render_briefs(st, user, today):
    user = deepcopy(user)
    owner = os_accounts.is_reporting_owner(user)
    reporting = os_accounts.can_access_reporting(user)
    def sports():
        if owner:
            def show(value):
                from home_sports_morning_brief import render
                render(st, user, today, snapshot=value)
            panel(st, user, today, 'Sports Updates', lambda: sports_data(today), show)
    if reporting:
        left, right = st.columns([3, 2], gap='medium')
        with left:
            sports()
        with right, st.container(key='home-meta-brief'):
            def show(value):
                from home_meta_morning_brief import render
                render(st, user, today, snapshot=value)
            panel(st, user, today, 'CRM Morning Brief', lambda: meta_data(today), show)
    else:
        sports()


def render_weekly(st, user, local_now, loader, renderer):
    user = deepcopy(user)
    def load():
        value = loader(user, datetime.now(local_now.tzinfo))
        value['completed_work_total'] = len(value.get('completed_work', []))
        value['completed_work'] = value.get('completed_work', [])[:100]
        return value
    panel(st, user, local_now.date(), "This Week's Work",
          load, lambda value: renderer(user, local_now, snapshot=value))
