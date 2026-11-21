"""Lazy, owner-only daily speed history."""


def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.can_access_page(user, 'Speed Optimisation'):
        st.error('Speed Optimisation is available only to the owner.')
        return
    st.title('Speed Optimisation')
    st.caption('Daily review: 1am Australia/Sydney · One section per run · Design and behaviour preserved')
    st.caption('Reviews include unused-code evidence and Supabase growth. Compact daily reports are retained for 90 days.')
    st.link_button('Publish daily report', '/ops/speed/publish')
    try:
        from speed_optimisation import Reports
        from supabase_backend import connect
        reports = Reports(connect).recent()
    except Exception:
        st.error('Speed reports are currently unavailable. No report has been assumed successful.')
        return
    if not reports:
        st.info('No speed reviews have been published yet. The first report will appear here after a completed review.')
        return
    st.dataframe([{'Date': r['date'], 'Section': r['section'], 'Status': r['status'],
                   'Summary': r['summary']} for r in reports], hide_index=True, use_container_width=True)
    for report in reports:
        with st.expander(f"{report['date']} · {report['section']} · {report['status']}"):
            st.write(report['summary'])
            st.caption('Source revision: ' + report['base_sha'])
            if report.get('live_sha'):
                st.caption('Verified live revision: ' + report['live_sha'])
            if report.get('measurements'):
                import statistics
                st.dataframe([{'Workflow': m['workflow'], 'Environment': m['environment'],
                               'Median ms': round(statistics.median(m['samples_ms']), 1),
                               'Samples': len(m['samples_ms']), 'Revision': m['revision']}
                              for m in report['measurements']], hide_index=True)
            for field, label in [('phases', 'Work phases'), ('tests', 'Validation'),
                                 ('files', 'Changed files'), ('cleanup_checks', 'Code cleanup'),
                                 ('storage_checks', 'Supabase storage review'), ('blockers', 'Blocked work')]:
                if report.get(field):
                    st.write(label)
                    for line in report[field]:
                        st.text(line)
