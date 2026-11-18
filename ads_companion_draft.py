"""Review the imported queued draft and repair targeting without re-generating."""
from uuid import UUID
import design_publish_ad as queue


def read(job_id, user):
    from product_upload_staff_queue import can_control_queues
    with queue.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (queue.PREFIX+str(UUID(job_id)),))
        row = cur.fetchone()
    if not row:
        raise ValueError('Queued ad not found.')
    value = row['value']
    if str((user or {}).get('id')) != value['requester'] and not can_control_queues(user):
        raise PermissionError('This ad draft belongs to another account.')
    queue.check_request(user, value['sport'], value['country'])
    return value


def render(job_id, user):
    import streamlit as st
    import ads_page
    import ads_direct_post
    from product_upload_services import Dropbox
    from ads_companion_transfer import resume

    try:
        value = read(job_id,user)
        from ads_companion_controls import stopped, action
        if stopped(job_id):
            st.info('This job is stopped. Its imported files and posting receipts are retained.')
            if st.button('Play / resume saved job'):
                action(user,job_id,'play')
                st.rerun()
            return
        if not value.get('result') or not value.get('folder'):
            st.info('The queued ad is waiting to be prepared.')
            if st.button('Refresh import status'):
                st.rerun()
            return
        result = value['result']
        st.header(result['product_name'])
        st.caption(queue.LABELS[value['stage']])
        if value.get('detail'):
            st.info(value['detail'])
        if st.button('Refresh import status'):
            st.rerun()
        dbx = Dropbox()
        copy_meta = dbx.metadata_if_present(value['folder']+'/ad_copy.csv')
        copy = ads_page.parse_instant_experience_copy_csv(queue._download(dbx,copy_meta,2*1024**2),result) if copy_meta else {}
        for col,(route,name) in zip(st.columns(3),queue.COVERS.items()):
            with col:
                st.subheader(name.removesuffix('.jpg').replace('-',' ').title())
                meta = dbx.metadata_if_present(value['folder']+'/'+name)
                if meta:
                    st.image(queue._download(dbx,meta,20*1024**2))
                else:
                    st.caption('Image not collected yet')
                if route in copy:
                    st.write(copy[route][0])
                else:
                    st.caption('Copy not collected yet')
        if value.get('targeting'):
            st.caption('Product set: '+value['targeting']['product_set_name']+' · Audience: '+value['targeting']['audience_name'])
        if value.get('posting_id'):
            st.link_button('Open existing Posting job','/?page=ads_posting&meta_posting_job='+value['posting_id'])
        elif value['stage']=='failed':
            workflow=st.session_state.setdefault('queued-ad-targeting:'+job_id,{'posting_settings':result.get('posting_settings') or value.get('targeting') or {}})
            settings, issues = ads_direct_post.render_settings(result,workflow)
            if st.button('Save targeting and resume import',disabled=bool(issues)):
                resume(job_id,user,settings=settings)
                st.rerun()
        else:
            st.caption('The companion will continue to Post now when all four original files and targeting pass verification. Ads are created paused for review.')
    except (ValueError,PermissionError) as error:
        st.error(str(error))
