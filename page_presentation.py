"""Opt-in native page presentation. No navigation, data access or state changes."""

COMPACT_PAGE_CSS = """
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) {
  padding-top: calc(var(--sc-topbar-height, 0px) + 12px) !important;
  padding-bottom: 24px !important;
  font-family: "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stElementContainer"]:has(.sc-compact-page-marker) {display:none;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {display:none;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stVerticalBlock"] {gap: .65rem;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) h1 {font-size:22px;line-height:1.3;padding:0;margin:0;font-weight:600;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) h2 {font-size:18px;line-height:1.4;padding:0;margin:0;font-weight:600;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) h3 {font-size:16px;line-height:1.4;padding:0;margin:0;font-weight:600;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stForm"] {padding:10px 12px;border-radius:6px;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stLinkButton"]) :is(button,a) {min-height:34px;border-radius:5px;font-size:14px;transition:background-color 100ms ease;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) :is(button,a,input,textarea):focus-visible {outline:2px solid #9a7937;outline-offset:2px;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) button:disabled {opacity:.55;cursor:not-allowed;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) hr {margin:4px 0;border-color:#e4e2da;}
[data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) details summary {min-height:34px;padding:6px 10px;}
@media (max-width:640px), (pointer:coarse) {
 [data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) :is([data-testid="stButton"], [data-testid="stFormSubmitButton"], [data-testid="stLinkButton"]) :is(button,a) {min-height:44px;}
}
@media (max-width:640px) {
 [data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
 [data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) [data-testid="stColumn"] {min-width:0 !important;flex:1 1 100% !important;width:100% !important;}
}
@media (prefers-reduced-motion:reduce) {
 [data-testid="stMainBlockContainer"]:has(.sc-compact-page-marker) :is(button,a) {transition:none !important;}
}
"""


SPACING_PAGE_CSS = """
[data-testid="stMainBlockContainer"]:has(.sc-spacing-page-marker) {
  padding-top: calc(var(--sc-topbar-height, 0px) + 12px) !important;
  padding-bottom: 24px !important;
}
[data-testid="stMainBlockContainer"]:has(.sc-spacing-page-marker) [data-testid="stElementContainer"]:has(.sc-spacing-page-marker) {display:none;}
[data-testid="stMainBlockContainer"]:has(.sc-spacing-page-marker) [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {display:none;}
"""


def inject_page_spacing(st, *, top_clearance=12):
    """Remove verified content gaps while retaining a modern module's controls."""
    css = SPACING_PAGE_CSS.replace('+ 12px', f'+ {int(top_clearance)}px')
    st.markdown('<style>' + css + '</style><span class="sc-spacing-page-marker" aria-hidden="true"></span>', unsafe_allow_html=True)


def inject_compact_page(st):
    """Apply only while this page's marker is mounted; never style the shell."""
    st.markdown('<style>' + COMPACT_PAGE_CSS + '</style><span class="sc-compact-page-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
