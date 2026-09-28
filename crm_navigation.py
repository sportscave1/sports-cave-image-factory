"""CRM navigation metadata only: safe to import in the OS shell."""

PAGES = (
    ('crm_campaigns_manage', 'CRM Campaigns', 'Campaigns'),
    ('crm_automations_manage', 'CRM Automations', 'Automations'),
    ('crm_settings_view', 'CRM Settings', 'Settings'),
    ('crm_customers_view', 'CRM Customers', 'Customers'),
    ('crm_segments_view', 'CRM Segments', 'Segments'),
    ('crm_templates_manage', 'CRM Templates', 'Templates'),
    ('crm_reports_view', 'CRM Reports', 'Reports'),
)
ROUTES = tuple(p[1] for p in PAGES)
PAGE_KEYS = {p[1]: p[0] for p in PAGES}
LABELS = {p[1]: p[2] for p in PAGES}
DEFAULT_ROUTE = ROUTES[0]
SIDEBAR_ROUTES=('Email','CRM Campaigns','CRM Automations')
EMAIL_LABELS={'Email':'Inbox','CRM Campaigns':'Campaigns','CRM Automations':'Automations'}
EMAIL_DEFAULT_ROUTE='Email'
SETTINGS_ALIASES={'CRM Customers':'Customers','CRM Segments':'Segments','CRM Templates':'Templates','CRM Reports':'Reports'}


def navigation_allowed(state,current,target):
    """Metadata-only unsaved-draft guard; no DB/Shopify calls in the OS shell."""
    editor=state.get('campaign_editor');saved=state.get('campaign_saved') or {}
    pending=editor and (editor.get('document')!=saved.get('document') or editor.get('name')!=saved.get('name'))
    if current=='CRM Campaigns' and target!=current and pending:
        state['crm_requested_route']=target
        return False
    return True


def require(user, key):
    import os_accounts
    if key=='crm_settings_view' and os_accounts.account_is_active(user) and any(k in os_accounts.permission_keys(user) for k,_,_ in PAGES):return
    if not os_accounts.account_is_active(user) or not (
        os_accounts.is_admin(user) or key in os_accounts.permission_keys(user)
    ):
        raise PermissionError('Your account does not have access to this CRM action.')
