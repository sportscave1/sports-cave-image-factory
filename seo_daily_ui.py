"""Single SEO review page; expensive editors load only when opened."""
import json
import streamlit as st
import os_accounts
import seo_navigation as nav
import seo_phase1 as model
import home_seo_report as report

EDITOR_ROUTES = (nav.SEO_ANALYTICS_ROUTE, nav.SEO_PLAN_ROUTE, nav.SEO_REVIEW_ROUTE, nav.SEO_HISTORY_ROUTE)


def _section_changed(route):
    if st.session_state.get('seo-single-' + route):
        for other in EDITOR_ROUTES:
            if other != route:
                st.session_state['seo-single-' + other] = False


@st.cache_data(ttl=30, show_spinner=False)
def _latest():
    return report.latest()


def render(user, state, store, reports, navigate, *, legacy_route=None):
    import seo_phase1_ui as ui
    from sports_sales_calendar import sydney_date
    st.title('SEO')
    st.caption('Daily review · strategy · evidence · plan · results | 4:00 am Sydney')
    @st.fragment(run_every=30)
    def edition_view():
        saved = {}
        if not model.local_mode():
            try:
                saved = _latest()
            except Exception:
                st.warning('Saved SEO report is temporarily unavailable. Your plan and tools remain available.')
        st.html(report.compact_html(saved, sydney_date()))
        if saved:
            st.subheader('Today’s priority')
            st.write(saved['next_action'])
            for row in saved.get('opportunities', []):
                with st.expander(row['market'] + ' · ' + row['query']):
                    st.write(row['url'])
                    st.write('Evidence: ' + row['evidence'])
                    st.write('Availability: ' + row['availability'])
                    st.write('Proposed action: ' + row['action'])
                    if st.button('Add to SEO plan', key='seo-daily-plan-' + row['market'] + row['url'] + row['query']):
                        model.create_task(state, title=row['action'], target=row['url'], query=row['query'],
                            intent='daily-seo-opportunity', evidence={'explanation': row['evidence'], 'availability': row['availability']},
                            context={'market': row['market'], 'report_date': saved['date'], 'start': saved['period_start'], 'end': saved['period_end']}, actor=user)
                        ui.save(store, state, user)
                        st.rerun()
            st.download_button('Download daily report', json.dumps(saved, ensure_ascii=False, indent=2),
                               file_name='seo-' + saved['date'] + '.json', mime='application/json')
    edition_view()
    if not model.local_mode():
        from seo_companion_ui import results
        results(user)
    active = [r for r in state['plan_items'] if r.get('status') in model.ACTIONABLE and
              (not r.get('admin_only') or os_accounts.is_admin(user))]
    cols = st.columns(3)
    cols[0].metric('Active plan items', len(active))
    cols[1].metric('Ready for review', sum(r.get('status') == 'Ready for review' for r in active))
    cols[2].metric('Technical priorities', sum(r.get('work_type') == 'Technical fix' for r in active))
    evidence = st.session_state.get('seo-phase1-scan-evidence')
    if st.button('Evaluate loaded search opportunities', disabled=not evidence):
        count = model.scan(state, evidence['rows'], evidence['context'], actor=user)
        ui.save(store, state, user)
        st.success(f'Scan completed: {count} new plan items.')
    with st.expander('Daily SEO strategy', expanded=True):
        st.write(report.STRATEGY)
    # Opening one editor leaves the other sections untouched and avoids unnecessary reads.
    sections = (
        ('Search evidence and analytics', lambda: ui.analytics(user, store, reports), nav.SEO_ANALYTICS_ROUTE),
        ('SEO plan and tools', lambda: ui.plan(user, state, store, navigate), nav.SEO_PLAN_ROUTE),
        ('Content and approval review', lambda: ui.review(user, state, store), nav.SEO_REVIEW_ROUTE),
        ('Report archive and activity', lambda: _history(user, state), nav.SEO_HISTORY_ROUTE),
    )
    if st.session_state.get('seo-single-legacy-route') != legacy_route:
        st.session_state['seo-single-legacy-route'] = legacy_route
        if legacy_route in (nav.SEO_PLAN_ROUTE, nav.SEO_REVIEW_ROUTE, nav.SEO_HISTORY_ROUTE):
            st.session_state['seo-single-' + legacy_route] = True
            _section_changed(legacy_route)
    for label, callback, permission in sections:
        if not os_accounts.can_access_page(user, permission):
            continue
        panel = st.expander(label, key='seo-single-' + permission,
                            expanded=bool(st.session_state.get('seo-single-' + permission)),
                            on_change=_section_changed, args=(permission,))
        if panel.open:
            with panel:
                callback()
    if navigate and os_accounts.can_access_page(user, 'Upload Companion'):
        if st.button('Open Companion', key='seo-open-companion'):
            navigate('Upload Companion')
            st.rerun()
    st.caption('Companion executes in Companion. A report or internal approval is separate from a verified live change.')


def _history(user, state):
    import seo_phase1_ui as ui
    if not model.local_mode():
        from supabase_backend import connect
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY key DESC LIMIT 30',
                            (report.HISTORY + '%',))
                editions = [row['value'] for row in cur.fetchall()]
            for edition in editions:
                with st.expander(edition['date'] + ' · ' + edition['summary'][:100]):
                    st.json(edition)
        except Exception:
            st.warning('Report archive unavailable; saved activity is shown below.')
    ui.history(user, state)
