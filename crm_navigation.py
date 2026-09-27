"""CRM navigation metadata only: safe to import in the OS shell."""

PAGES = (
    ('crm_customers_view', 'CRM Customers', 'Customers'),
    ('crm_segments_view', 'CRM Segments', 'Segments'),
    ('crm_automations_manage', 'CRM Automations', 'Automations'),
    ('crm_campaigns_manage', 'CRM Campaigns', 'Campaigns'),
    ('crm_templates_manage', 'CRM Templates', 'Templates'),
    ('crm_reports_view', 'CRM Reports', 'Reports'),
)
ROUTES = tuple(p[1] for p in PAGES)
PAGE_KEYS = {p[1]: p[0] for p in PAGES}
LABELS = {p[1]: p[2] for p in PAGES}
DEFAULT_ROUTE = ROUTES[0]


def require(user, key):
    import os_accounts
    if not os_accounts.account_is_active(user) or not (
        os_accounts.is_admin(user) or key in os_accounts.permission_keys(user)
    ):
        raise PermissionError('Your account does not have access to this CRM action.')
