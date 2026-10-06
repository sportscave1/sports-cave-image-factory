"""Small admin settings page for public Shopify artwork only."""
import os_accounts
import image_protection


def render(st, user):
    if not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
        st.error('Administrator access required.')
        return
    st.title('IMAGE PROTECTION')
    st.caption('Deterrence for artwork displayed on the public Sports Cave website.')
    st.info('Browser protection can discourage casual saving and copying but cannot completely prevent operating-system screenshots or determined downloads.')
    try:
        policy = image_protection.load_policy()
    except Exception:
        st.error('Image protection settings are unavailable. Please try again later.')
        return
    with st.form('website-image-protection'):
        labels = (
            ('enabled', 'Enable Website Image Protection'),
            ('disableRightClick', 'Disable right-click on protected artwork'),
            ('preventImageDragging', 'Disable image dragging'),
            ('preventSelection', 'Disable text/image selection on artwork'),
            ('aggressiveCopyDeterrence', 'Disable copy on protected artwork'),
            ('mobileTouchProtection', 'Disable mobile WebKit long-press / touch callout'),
            ('protectPrinting', 'Hide protected artwork when printing'),
            ('blockSaveShortcuts', 'Block Save Image / Ctrl+S / Cmd+S while artwork is targeted'),
            ('showCopyrightMessage', 'Show a small copyright warning'),
            ('visibleWatermark', 'Show a subtle Sports Cave watermark'),
        )
        values = {key:st.checkbox(label,value=policy[key]) for key,label in labels}
        save = st.form_submit_button('Save image protection',type='primary')
    if save:
        try:
            image_protection.save_policy(user,values)
            st.success('Website settings saved. Allow up to 90 seconds for cached configuration to refresh.')
        except Exception:
            st.error('Settings could not be saved. No changes were confirmed.')
    st.caption('Installed only on the Shopify storefront. These controls do not affect Sports Cave OS.')
