"""Admin-only settings integrated into the existing top-right Settings menu."""
import os_accounts
from security_protection import STORE, cached_policy


def render(st,user,sid):
    STORE.admin(user.get('id'))
    st.title('Security & Protection')
    st.caption('App privacy, sessions and storefront artwork protection.')
    policy=cached_policy()
    st.info('Browser capture limitation · Web browsers cannot reliably prevent operating-system screenshots. Copying and printing controls provide deterrence.')
    with st.expander('Security status',expanded=True):
        st.write('Backend authorisation: existing account and permission controls')
        st.write('Security settings and audit: administrator only')
        st.write('Windows Desktop: native capture exclusion implemented; installed package verification required')
        st.html('<span id="sc-native-capture-state">Current runtime: Browser capture limitation</span><script>const state=window.__SC_NATIVE_CAPTURE_PROTECTION;const label=document.getElementById("sc-native-capture-state");if(state && label)label.textContent=state.excluded?"Windows native capture exclusion: enabled and affinity verified":"Windows native capture exclusion: unavailable";</script>',unsafe_allow_javascript=True)
        st.write('Android / iOS: no native application installed by this project')
        st.write('MFA / passkeys: authentication provider configuration required')
    with st.expander('Verify password for sensitive actions'):
        with st.form('security-reauth'):
            password=st.text_input('Current password',type='password')
            submitted=st.form_submit_button('Verify password')
        if submitted:
            try:STORE.reauthenticate(user['id'],sid,password);st.success('Verified for five minutes.')
            except PermissionError as error:st.error(str(error))
    values=dict(policy)
    with st.form('security-policy'):
        with st.expander('App protection',expanded=True):
            for key,label in (('appRightClick','Disable right click'),('appImageDragging','Prevent image dragging'),('appSelection','Restrict protected text selection'),('appPrinting','Protect artwork printing'),('appCopyDeterrence','Aggressive artwork copy deterrence'),('blurOnFocusLoss','Blur sensitive content when focus is lost'),('appWatermark','Security watermark')):
                values[key]=st.checkbox(label,value=policy[key],key="security-"+key)
        with st.expander('Storefront protection'):
            for key,label in (('enabled','Storefront protection enabled'),('disableRightClick','Disable storefront right click'),('preventImageDragging','Prevent artwork dragging'),('preventSelection','Prevent artwork selection'),('protectPrinting','Protect artwork printing'),('blockSaveShortcuts','Block common save shortcuts'),('mobileTouchProtection','Disable WebKit image touch callout'),('aggressiveCopyDeterrence','Aggressive artwork copy deterrence'),('showCopyrightMessage','Show copyright message'),('visibleWatermark','Baked-in watermark for new web derivatives')):
                values[key]=st.checkbox(label,value=policy[key],key="security-"+key)
            st.caption('Never serve print masters · Always on. Existing public images require a separate audit and confirmed remediation.')
        with st.expander('Image protection'):
            edges=[1200,1600,1800,2000,2400]
            values['maxImageEdge']=st.selectbox('Public maximum long edge',edges,index=edges.index(policy['maxImageEdge']))
            for key,label,options in (('watermarkOpacity','Watermark opacity',['Low','Medium','High']),('watermarkPosition','Watermark position',['corner','centre','repeated'])):
                values[key]=st.selectbox(label,options,index=options.index(policy[key]))
        with st.expander('Session security'):
            options=[5,10,15,30,60,0]
            values['autoLockMinutes']=st.selectbox('Lock after',options,index=options.index(policy['autoLockMinutes']),format_func=lambda v:f'{v} minutes' if v else 'Never')
            values['sensitiveReauth']=st.checkbox('Require sensitive-action password verification',value=policy['sensitiveReauth'])
        save=st.form_submit_button('Save protection settings',type='primary')
    if save:
        try:STORE.save_policy(user['id'],values,sid);st.success('Protection settings saved.');st.rerun()
        except (ValueError,PermissionError) as error:st.error(str(error))
    with st.expander('Existing public product image audit'):
        st.caption('Read-only Shopify audit, 25 products per request. Dimensions flag risk; they do not prove that an image is a master. No images are replaced automatically.')
        restart_audit=st.button('Run image audit')
        next_audit=st.button('Audit next 25 products',disabled=not st.session_state.get('security_image_audit_cursor'))
        if restart_audit or next_audit:
            import shopify_sync
            from protected_web_images import classify_public_image
            try:
                page=shopify_sync.fetch_catalog_page(page_size=25,after=st.session_state.get('security_image_audit_cursor') if next_audit else None)
                results=[]
                for product in page['products']:
                    for image in product.get('images',[]):
                        results.append({'Product':product['title'],'Status':classify_public_image(image.get('width'),image.get('height'),image.get('url'),policy['maxImageEdge']),'Width':image.get('width'),'Height':image.get('height'),'Admin URL':product.get('admin_url','')})
                st.session_state['security_image_audit']=results[:250]
                st.session_state['security_image_audit_remaining']=page['has_next_page']
                st.session_state['security_image_audit_cursor']=page['end_cursor'] if page['has_next_page'] else None
                STORE.audit('IMPORTANT_ADMIN_ACTION',user['id'],'public_image_audit_read',result='checked',session_id=sid)
            except Exception:st.error('Shopify image audit unavailable. No images were changed.')
        if 'security_image_audit' in st.session_state:
            st.dataframe(st.session_state['security_image_audit'],use_container_width=True,hide_index=True)
            if st.session_state.get('security_image_audit_remaining'):st.caption('More products remain. Use Audit next 25 products; this table shows only the current batch.')
            st.caption('Remediation: review the product in Shopify Admin, generate a protected replacement through the OS export pipeline, then explicitly replace the public media. Keep the original in private storage.')
        from pathlib import Path
        report=Path(__file__).parent/'docs/PUBLIC_IMAGE_AUDIT_20261005.csv'
        if report.exists():
            st.download_button('Download reviewed 5 Oct 2026 audit',report.read_bytes(),file_name=report.name,mime='text/csv')
    with st.expander('Sessions & devices'):
        rows=STORE.q('SELECT s.id,s.user_id,s.device,s.created_at,s.last_activity_at,s.revoked_at,u.display_name FROM os_security_sessions s JOIN os_users u ON u.id=s.user_id ORDER BY s.created_at DESC LIMIT 50')
        for row in rows:
            st.write(f"{row.get('display_name') or 'Account'} · {row['device'] or 'Browser / app'} · {'Current device' if row['id']==sid else 'Other session'}")
            st.caption(f"Created {row['created_at']} · Activity {row['last_activity_at']}")
            if not row['revoked_at'] and row['id']!=sid and st.button('Revoke session',key='revoke-'+row['id']):
                try:STORE.revoke(user['id'],sid,row['id']);st.rerun()
                except PermissionError as error:st.error(str(error))
        if st.button('Sign out other sessions'):
            try:
                for row in rows:
                    if str(row['user_id'])==str(user['id']) and row['id']!=sid and not row['revoked_at']:STORE.revoke(user['id'],sid,row['id'])
                st.success('Other sessions revoked.')
            except PermissionError as error:st.error(str(error))
    with st.expander('Audit & security log'):
        search=st.text_input('Search resource')
        event=st.text_input('Event filter')
        users=STORE.q('SELECT id,display_name FROM os_users WHERE account_status=\'active\' ORDER BY display_name LIMIT 100')
        user_filter=st.selectbox('User',['All users']+[str(u['id']) for u in users],format_func=lambda v:next((u['display_name'] for u in users if str(u['id'])==v),v))
        from datetime import date,timedelta
        since=st.date_input('From date',value=date.today()-timedelta(days=30))
        rows=STORE.q('SELECT occurred_at,user_id,event,resource,result FROM os_security_audit WHERE resource ILIKE %s AND event ILIKE %s AND occurred_at>=%s AND (%s=\'All users\' OR user_id::text=%s) ORDER BY occurred_at DESC LIMIT 100',('%'+search[:160]+'%','%'+event[:80]+'%',since,user_filter,user_filter))
        st.dataframe(rows,use_container_width=True,hide_index=True)
        # Reuse existing application audit records for account/certificate work;
        # don't duplicate financial/customer payloads in the security store.
        application_events=STORE.q("SELECT created_at,actor,event_type,entity_type FROM audit_logs WHERE created_at>=%s AND event_type IN ('account_created','account_updated','account_remote_logout','account_permanently_removed','edition_order_manual_override','manual_certificate_saved','manual_certificate_removed') AND event_type ILIKE %s ORDER BY created_at DESC LIMIT 50",(since,'%'+event[:80]+'%'))
        if application_events:
            st.caption('Account and certificate events from the existing audit trail')
            st.dataframe(application_events,use_container_width=True,hide_index=True)
