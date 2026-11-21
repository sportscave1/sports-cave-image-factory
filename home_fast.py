"""Home panels consume bounded display snapshots, independent of shell rendering."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
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
    initial = SNAPSHOTS.read(key, loader)
    waiting = initial['value'] is None

    # Replace one owned slot on every refresh, including loading/stale transitions.
    # Never append refreshed HTML into the previous panel's container.
    target = st.empty()

    @st.fragment(run_every=1 if waiting else 30)
    def content():
        with target.container():
            result = SNAPSHOTS.read(key, loader)
            value = result['value']
            if value is None:
                st.caption(name + (' · temporarily unavailable; retrying' if result['state'] == 'unavailable'
                                   else ' · loading saved information…'))
                return
            if waiting:
                # One rerun switches the initial short refresh to the idle cadence.
                st.rerun()
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
