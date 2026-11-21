"""Administrator workspace: review listings, enquiries and Git-backed website publication."""
import base64
from collections import Counter
from copy import deepcopy

from marketplace import (BASE_PATH, PUBLIC_ORIGIN, CATEGORIES, deployed_site, money,
                         site_config, listing_url, fee_quote)
from marketplace_store import MarketplaceStore
from marketplace_publish import publish_website
from prompt_releases import GitStore, ReleaseError


def render_page(user, store=None):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_admin(user):
        st.error('Marketplace is available to administrators only.')
        return
    store = store or MarketplaceStore()
    st.html('''<style>.st-key-marketplace-workspace h1{font-size:2rem!important;letter-spacing:-.04em}
      .st-key-marketplace-workspace [data-testid="stMetricValue"]{font-size:1.6rem!important}
      .st-key-marketplace-workspace .stTabs{margin-top:8px}
      .st-key-marketplace-workspace [data-testid="stVerticalBlock"]{gap:.8rem}</style>''')
    with st.container(key='marketplace-workspace'):
        heading, visit = st.columns([4, 1], vertical_alignment='center')
        heading.title('Marketplace')
        visit.link_button('Open website', PUBLIC_ORIGIN + BASE_PATH, icon=':material/open_in_new:', width='stretch')
        try:
            rows = store.listings()
            enquiries = store.enquiries()
        except Exception:
            st.error('Marketplace storage is temporarily unavailable. No successful save is confirmed.')
            return
        counts = Counter(row['status'] for row in rows)
        for column, label, value in zip(st.columns(3), ('Awaiting review', 'Published listings', 'New enquiries'),
                (counts['pending'], counts['published'], sum(r['status'] == 'new' for r in enquiries))):
            column.metric(label, value)
        tabs = st.tabs(['Listings', 'Enquiries', 'Website & publish', 'Outreach'], on_change='rerun', key='marketplace-tabs')
        for name, tab in zip(('listings', 'enquiries', 'website', 'outreach'), tabs):
            if not tab.open:
                continue
            with tab:
                if name == 'listings':
                    render_listings(st, store, rows, user)
                elif name == 'enquiries':
                    render_enquiries(st, store, enquiries)
                elif name == 'outreach':
                    from marketplace_outreach import render
                    render(st, store.connect)
                else:
                    render_website(st, store)


def render_listings(st, store, rows, user):
    status = st.selectbox('Show', ('pending', 'published', 'withdrawn', 'declined'),
                          format_func=lambda v: {'pending': 'Awaiting review', 'published': 'Published', 'withdrawn': 'Withdrawn', 'declined': 'Declined'}[v])
    filtered = [row for row in rows if row['status'] == status]
    if not filtered:
        st.info('No items here yet. Seller submissions arrive from the website.')
        return
    selected = st.selectbox('Item', [r['id'] for r in filtered],
        format_func=lambda key: next(f'{r["title"]} · {money(r["price_cents"])}' for r in filtered if r['id'] == key))
    row = next(r for r in filtered if r['id'] == selected)
    detail, photos = st.columns([1.2, 1])
    with detail:
        st.subheader(row['title'])
        st.caption(f'{CATEGORIES[row["category"]]} · {row["sport"]} · {row["condition"]}')
        st.write(row['description'])
        if row.get('provenance'):
            st.caption('Provenance supplied by seller')
            st.write(row['provenance'])
        st.write(f'Seller: {row["seller_name"]} · {row["seller_type"]}')
        st.text(row['seller_email'])
        st.caption(row['location'])
        quote = fee_quote(row['price_cents'])
        st.caption(f'Asking {money(row["price_cents"])} · Postage {money(row["shipping_cents"])} · Indicative 5% fee {money(quote["fee_cents"])}')
    with photos:
        for i, column in enumerate(st.columns(2)):
            image = store.photo(row['id'], i, public=False)
            if image:
                column.image(base64.b64decode(image), width='stretch')
        if row['photo_count'] > 2:
            with st.expander('More photographs'):
                for i in range(2, row['photo_count']):
                    image = store.photo(row['id'], i, public=False)
                    if image:
                        st.image(base64.b64decode(image), width='stretch')
    if status in ('pending', 'withdrawn'):
        checked = st.checkbox('I reviewed the photos, condition, seller and provenance. The listing is suitable to publish.', key='review-' + row['id'])
        approve, decline = st.columns(2)
        action = 'published' if approve.button('Approve & publish listing', type='primary', disabled=not checked, width='stretch') else None
        if decline.button('Decline listing', width='stretch'):
            action = 'declined'
    elif status == 'published':
        st.link_button('View public listing', PUBLIC_ORIGIN + listing_url(row))
        action = 'withdrawn' if st.button('Withdraw listing') else None
    else:
        action = None
    if action:
        try:
            store.moderate(row['id'], action, row['revision'], user.get('id', 'admin'))
            st.rerun()
        except Exception as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else 'Could not update this listing. Reload before retrying.')
    st.caption('Listings accept enquiries. Checkout, seller verification and payments are not enabled.')


def render_enquiries(st, store, rows):
    include_handled = st.toggle('Include handled enquiries', value=False)
    rows = [row for row in rows if include_handled or row['status'] == 'new']
    if not rows:
        st.info('Buyer enquiries will appear here.')
        return
    enquiry_id = st.selectbox('Enquiry', [r['id'] for r in rows],
        format_func=lambda key: next(r['item_title'] + ' · ' + r['name'] for r in rows if r['id'] == key))
    row = next(r for r in rows if r['id'] == enquiry_id)
    st.subheader(row['item_title'])
    st.text(row['name'] + ' · ' + row['email'])
    st.write(row['message'])
    seller = store.listing(row['listing_id'])
    if seller:
        st.caption('Seller contact (private)')
        st.text(seller['seller_name'] + ' · ' + seller['seller_email'])
    st.caption('Received ' + row['created_at'][:16].replace('T', ' ') + ' UTC')
    if row['status'] == 'new' and st.button('Mark handled'):
        store.resolve_enquiry(row['id'])
        st.rerun()


def render_website(st, store):
    deployed = deployed_site()
    draft = store.draft(deployed)
    receipt = store.receipt()
    # A completed release becomes the next editing baseline.
    if receipt and receipt['release_id'] == deployed['release_id'] and draft['base'] != deployed:
        draft = store.save_draft({**draft['config'], 'release_id': deployed['release_id']}, deepcopy(deployed), draft['revision'])
    client = GitStore()
    connected = bool(client.token)
    st.caption('GitHub main → existing Sports Cave OS Render service · Marketplace website only')
    left, right = st.columns([1.5, 1])
    with left:
        with st.form('marketplace-website-settings'):
            headline = st.text_input('Headline', value=draft['config']['headline'], max_chars=80)
            description = st.text_area('Short description', value=draft['config']['description'], max_chars=160, height=90)
            intake = st.toggle('Accept seller submissions', value=draft['config']['intake_open'])
            saved = st.form_submit_button('Save website draft', width='stretch')
        if saved:
            try:
                config = site_config({**draft['config'], 'headline': headline, 'description': description, 'intake_open': intake})
                draft = store.save_draft(config, draft['base'], draft['revision'])
                st.success('Draft saved. The public website is unchanged until published.')
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else 'Draft storage unavailable. Save is not confirmed.')
    with right:
        st.subheader('Saved website draft')
        st.write(draft['config']['headline'])
        st.caption(draft['config']['description'])
        st.caption('Seller intake: ' + ('Open' if draft['config']['intake_open'] else 'Paused'))
        if not connected:
            st.info('Connect PROMPTS_GITHUB_TOKEN in the existing Render service to publish. This uses the same server connection as Prompts.')
        pending = bool(receipt and receipt['release_id'] != deployed['release_id'])
        changed = draft['config'] != draft['base']
        if st.button('Publish website', type='primary', disabled=not connected or not changed or pending or bool(draft.get('attempt')), width='stretch'):
            try:
                # Persist a stable attempt ID before the network request, so a lost
                # response can be reconciled without publishing the same draft twice.
                attempt = store.begin_publish(draft['revision'])
                st.session_state['marketplace-publish-attempt'] = attempt
                result = publish_website(attempt, client)
                store.receipt(result)
                st.session_state.pop('marketplace-publish-attempt', None)
                st.success('Published to GitHub. Render is deploying the website update.')
                st.rerun()
            except (ValueError, ReleaseError) as exc:
                st.error(str(exc))
            except Exception:
                st.error('Publication may have reached GitHub. Check release status before retrying.')
        interrupted = {**draft, **draft['attempt']} if draft.get('attempt') else st.session_state.get('marketplace-publish-attempt')
        if interrupted and st.button('Reconcile interrupted publish', width='stretch'):
            try:
                result = publish_website(interrupted, client)
                store.receipt(result)
                st.session_state.pop('marketplace-publish-attempt', None)
                st.rerun()
            except (ValueError, ReleaseError) as exc:
                st.error(str(exc))
        if interrupted and st.button('Check and clear failed publish attempt', width='stretch'):
            try:
                source, _ = client.read('static/marketplace/site.json', client.head())
                import json
                current = json.loads(source)
                if current.get('release_id') == interrupted['release_id']:
                    st.warning('This release reached GitHub. Reconcile it to continue.')
                else:
                    store.cancel_publish(interrupted['release_id'])
                    st.session_state.pop('marketplace-publish-attempt', None)
                    st.rerun()
            except ReleaseError as exc:
                st.error(str(exc))
        st.link_button('View live website', PUBLIC_ORIGIN + BASE_PATH, width='stretch')
    if receipt:
        live = receipt['release_id'] == deployed['release_id']
        st.success('Website release is live in this OS build.') if live else st.info('Website publish is awaiting the new Render build. Refresh after deployment.')
        st.link_button('GitHub release ' + receipt['commit'][:8], 'https://github.com/sportscave1/sports-cave-image-factory/commit/' + receipt['commit'])
    st.link_button('Render deployment status', 'https://dashboard.render.com/web/srv-d8kl4on7f7vs73dvavv0')
    with st.expander('Connect from the Sports Cave shop'):
        st.caption('Use this public URL for the shop’s Marketplace navigation link.')
        st.code(PUBLIC_ORIGIN + BASE_PATH, language=None)
    with st.expander('Website updates for Codex'):
        st.code('Update Sports Cave Marketplace in its isolated task worktree. Keep the Sports Cave Montserrat, charcoal and gold styling; minimal copy; compact responsive layout; server-rendered SEO and schema. Public routes: /marketplace. Admin: marketplace_page.py. Website: marketplace_views.py and static/marketplace/. Preserve private submissions and the approval gate. Run focused marketplace tests and validate_render_topology.py. Publish only when explicitly authorised, through the existing GitHub main → sports-cave-os Render service srv-d8kl4on7f7vs73dvavv0.', language=None, wrap_lines=True)
