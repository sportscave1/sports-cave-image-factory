"""Controls live in Companion; audit evidence and decisions live on SEO."""
import json
import streamlit as st
import os_accounts
import seo_companion as jobs


def controls(user):
    if not jobs.permitted(user):
        st.info('The reporting owner controls daily SEO audits.')
        return
    st.subheader('SEO queue')
    st.caption('Daily reports queue public storefront and inbound-link audits. Runs on the hosted Companion worker; this browser can be closed.')

    @st.fragment(run_every=15)
    def queue():
        try:
            data = jobs.snapshot()
        except Exception:
            st.warning('SEO queue unavailable. Retry after the shared store reconnects.')
            return
        enabled = data['settings'].get('enabled', False)
        st.write('Daily SEO audits: ' + ('Playing' if enabled else 'Paused'))
        label = 'Pause daily SEO audits' if enabled else 'Start daily SEO plan'
        if st.button(label, key='seo-companion-control'):
            try:
                jobs.configure(user, not enabled)
                st.rerun()
            except (PermissionError, ValueError) as error:
                st.error(str(error))
        st.caption('Start queues today’s published plan immediately and future reports automatically. Pause stops new starts; an active read-only audit finishes. Proposals never publish storefront changes.')
        for job in data['jobs']:
            with st.container(border=True):
                st.write(job['date'] + ' · ' + job['stage'].replace('_', ' ').title())
                st.write(job['instruction'])
                if job.get('progress'):
                    st.caption(json.dumps(job['progress']))
                if job.get('error'):
                    st.warning(job['error'])
                result = job.get('result')
                if result:
                    st.caption(f"{len(result['pages'])} pages checked · {len(result['links'])} matching link occurrences · {len(result['proposals'])} proposals · {len(result['gaps'])} coverage gaps")
        if not data['jobs']:
            st.info('No SEO audit has been queued yet. Publish a daily SEO report, then press Start.')
        st.link_button('Review SEO findings and proposed fixes', '/?page=seo')
    queue()


def results(user):
    if not os_accounts.can_access_page(user, 'seo'):
        return

    @st.fragment(run_every=15)
    def display():
        st.subheader('Companion results and proposed fixes')
        try:
            data = jobs.snapshot()
        except Exception:
            st.warning('Companion results are temporarily unavailable.')
            return
        if not data['jobs']:
            st.info('Start daily SEO work from Companion → SEO queue. Findings and review decisions return here.')
            return
        selected = st.selectbox('Audit run', data['jobs'], format_func=lambda j: j['date'] + ' · ' + j['stage'].replace('_', ' '),
                                key='seo-companion-result-run')
        st.write(selected['instruction'])
        result = selected.get('result')
        if not result:
            st.caption('Status: ' + selected['stage'].replace('_', ' '))
            if selected.get('progress'):
                st.write(selected['progress'])
            if selected.get('error'):
                st.warning(selected['error'])
            return
        st.caption(f"Finished {selected['finished_at']} · {len(result['pages'])} source pages checked · {result['remaining_sources']} remaining discovered sources · {result['requests']} requests · {result['storefront_changes']} storefront changes")
        st.write(result['scope'])
        st.write('Coverage: ' + ('All discovered in-scope sources checked.' if result['coverage_complete'] else 'Partial — see coverage gaps.'))
        st.caption(result['limitations'])
        st.caption(result['deferred_work'])
        for target in result['targets']:
            st.write(target['url'] + ' · HTTP ' + str(target['status'] if target['status'] is not None else 'unverified'))
            if target['findings']:
                with st.expander('Technical observations · ' + target['url']):
                    st.dataframe(target['findings'], hide_index=True, width='stretch')
        if result['links']:
            st.dataframe(result['links'], hide_index=True, width='stretch')
        else:
            st.info('No matching inbound links were observed in the checked HTML. This does not establish that none exist outside the recorded scope.')
        for proposal in result['proposals']:
            with st.expander('Proposed fix ' + proposal['id'] + ' · ' + proposal['kind'].replace('_', ' '), expanded=True):
                st.write({key: value for key, value in proposal.items() if key not in ('id', 'review_status')})
                decisions = [r for r in data['reviews'] if r['job_id'] == selected['id'] and
                             r['proposal_id'] == proposal['id'] and r['revision'] == jobs.revision(result)]
                st.caption('Review: ' + (decisions[0]['decision'] if decisions else 'Awaiting review'))
                if jobs.permitted(user):
                    key = selected['id'] + ':' + proposal['id']
                    decision = st.selectbox('Your decision', ('Changes requested', 'Approved for implementation', 'Dismissed'),
                                            key='seo-fix-decision-' + key)
                    if st.button('Save review decision', key='seo-fix-save-' + key):
                        try:
                            jobs.review(user, selected['id'], proposal['id'], decision, jobs.revision(result))
                            st.rerun()
                        except (PermissionError, ValueError) as error:
                            st.error(str(error))
        st.caption('A saved approval records your decision. Applying storefront changes is a separate implementation step.')
        with st.expander('Pages checked and coverage gaps'):
            st.dataframe(result['pages'], hide_index=True, width='stretch')
            for gap in result['gaps']:
                st.write(gap)
        st.download_button('Download Companion audit', json.dumps(selected, indent=2),
                           file_name='seo-companion-' + selected['date'] + '.json', mime='application/json',
                           key='seo-companion-audit-download')
    display()
