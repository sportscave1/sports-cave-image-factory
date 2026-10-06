"""Lazy-loaded public storefront controls; never part of OS auth."""
import os_accounts
import image_protection as policy

DEV_PREVIEW = 'https://www.sportscaveshop.com/?preview_theme_id=189335863603'


def render(st, user):
    if not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
        st.error('Administrator access required.')
        return
    st.title('Image Protection')
    st.caption('Protect Sports Cave artwork and wall previews across the Shopify storefront.')
    st.caption('Browser protection discourages casual copying. Operating-system screenshots and determined downloads cannot be completely blocked.')
    try:
        values = policy.load_policy()
    except Exception:
        st.error('Settings are temporarily unavailable. The storefront remains usable.')
        return
    st.caption('Storefront settings: ' + ('Enabled' if values['enabled'] else 'Off') + ' · Script ' + policy.SCRIPT_VERSION)
    try:
        st.caption('Last config update: '+policy.last_updated())
    except Exception:
        st.caption('Last config update: unavailable')
    with st.form('website-image-protection'):
        result = dict(values)
        result['enabled'] = st.toggle('Enable Storefront Image Protection', value=values['enabled'])
        scope, actions, watermark = st.columns(3)
        with scope:
            st.markdown('**Protection scope**')
            for key, label in [('protectProductImages','Product, search and quick-view artwork'),('protectCollections','Collection artwork'),('protectHomepage','Homepage artwork'),('protectWallPreview','See It On Your Wall')]:
                result[key] = st.checkbox(label,value=values[key])
            result['screenshotDeterrence'] = st.checkbox('Screenshot deterrence',value=values['screenshotDeterrence'],help='Web browsers cannot completely block operating-system screenshots. Observable PrintScreen keys show a copyright notice only; camera and shopping remain uninterrupted.')
        with actions:
            st.markdown('**Artwork controls**')
            for key,label in [('disableRightClick','Disable image right-click'),('preventImageDragging','Disable image dragging'),('preventSelection','Disable artwork selection'),('aggressiveCopyDeterrence','Disable artwork copying'),('mobileTouchProtection','Block image long-press where practical'),('blockSaveShortcuts','Block common image-save shortcuts'),('protectPrinting','Print protection'),('showCopyrightMessage','Show copyright notice')]:
                result[key]=st.checkbox(label,value=values[key])
        with watermark:
            st.markdown('**Optional watermark**')
            result['visibleWatermark']=st.checkbox('Watermark storefront artwork',value=values['visibleWatermark'])
            result['wallPreviewWatermark']=st.checkbox('Watermark on-screen wall preview',value=values['wallPreviewWatermark'])
            result['watermarkText']=st.text_input('Watermark text',value=values['watermarkText'],max_chars=60)
            result['watermarkOpacity']=st.slider('Opacity',0.05,0.6,float(values['watermarkOpacity']),0.05)
            positions=['bottom-right','center']
            result['watermarkPosition']=st.selectbox('Position',positions,index=positions.index(values['watermarkPosition']))
            st.caption('On-screen only. Original artwork and official downloads stay unchanged.')
        save=st.form_submit_button('Save image protection',type='primary')
    if save:
        try:
            policy.save_policy(user,result)
            st.success('Saved. New page loads receive settings within 90 seconds; refresh already-open storefront pages.')
        except Exception:
            st.error('Settings could not be saved. No changes were confirmed.')
    with st.expander('Shopify installation & status',expanded=True):
        st.caption('Install once before </body> in layout/theme.liquid. Future settings are controlled here. Use the code box copy button.')
        st.code('<script src="'+policy.PUBLIC_ORIGIN+'/storefront-protection.js" defer></script>',language='html')
        st.link_button('Open Sports Cave DEV — Codex',DEV_PREVIEW)
        if st.button('Verify DEV installation'):
            from image_protection_status import verify_dev
            st.session_state['image_protection_install_check']=verify_dev()
        st.caption(st.session_state.get('image_protection_install_check') or 'Installation status: Unable to verify until checked. No background storefront polling.')
