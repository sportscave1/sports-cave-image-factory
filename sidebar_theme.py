"""Presentation-only sidebar theme. No routes, state, icons or data access."""

SIDEBAR_CSS = r"""
section[data-testid="stSidebar"] {
 --sidebar-bg-top:#151716; --sidebar-bg-bottom:#101211;
 --sidebar-panel:#272826; --sidebar-panel-hover:#30312e;
 --sidebar-text:#eeeeeb; --sidebar-muted:#9b9b95;
 --sidebar-border:rgba(255,255,255,.045);
 --sidebar-gold:#c9a33f; --sidebar-gold-light:#d6b44e; --sidebar-gold-text:#fff;
 --sc-sidebar-width:244px;
 width:var(--sc-sidebar-width) !important;min-width:var(--sc-sidebar-width) !important;max-width:min(var(--sc-sidebar-width),100vw) !important;
 font-family:"Segoe UI Variable","Segoe UI",system-ui,sans-serif;
 background:linear-gradient(165deg,var(--sidebar-bg-top),var(--sidebar-bg-bottom)) !important;
 border-right:1px solid var(--sidebar-border);
 height:calc(100dvh - var(--sc-topbar-height)) !important;
 top:var(--sc-topbar-height) !important;position:sticky !important;align-self:flex-start;
 color:var(--sidebar-text); color-scheme:dark;overflow-x:clip !important;
}
section[data-testid="stSidebar"] * {color:inherit !important;-webkit-text-fill-color:currentColor !important;}
section[data-testid="stSidebar"] [data-testid="stButton"] button * {color:inherit !important;-webkit-text-fill-color:currentColor !important;}
section[data-testid="stSidebar"] > div {height:100%;overflow-x:hidden;overflow-y:auto;padding:12px 0 0 !important;box-sizing:border-box;scrollbar-width:thin;scrollbar-color:#454641 transparent;}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {display:none !important;height:0 !important;min-height:0 !important;}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > div,
section[data-testid="stSidebar"] .block-container {min-height:100%;}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {padding:0 10px 12px;}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:2px !important;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-history-"],
section[data-testid="stSidebar"] div:has(> [class*="st-key-sidebar-history-"]) {display:none !important;}
section[data-testid="stSidebar"] .sc-sidebar-a11y {height:1px;margin:-1px;overflow:hidden;padding:0;position:absolute;width:1px;clip:rect(0,0,0,0);}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {margin-bottom:0;}
section[data-testid="stSidebar"] [data-testid="stButton"] {margin:0;}
section[data-testid="stSidebar"] [data-testid="stButton"] button {
 align-items:center;background:transparent !important;border:1px solid transparent !important;
 border-radius:7px !important;box-shadow:none !important;color:var(--sidebar-text) !important;
 cursor:pointer;display:flex;font-weight:500 !important;justify-content:flex-start;
 height:auto;min-height:35px;padding:6px 10px !important;text-align:left;width:100%;
 transition:background-color 100ms ease,color 100ms ease;
}
section[data-testid="stSidebar"] [data-testid="stButton"] button > div {justify-content:flex-start;gap:8px;width:100%;}
section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {background:var(--sidebar-panel-hover) !important;}
section[data-testid="stSidebar"] [data-testid="stButton"] button:focus-visible {outline:2px solid var(--sidebar-gold) !important;outline-offset:-2px;}
section[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"],
section[data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
 background:linear-gradient(105deg,#b99436,#d0aa46) !important;color:var(--sidebar-gold-text) !important;font-weight:600 !important;
}
section[data-testid="stSidebar"] [data-testid="stButton"] button p,
section[data-testid="stSidebar"] [data-testid="stButton"] button span {color:inherit !important;font-size:14px;letter-spacing:0;line-height:1.3;overflow-wrap:anywhere;white-space:normal;}
section[data-testid="stSidebar"] [data-testid="stButton"] button [data-testid="stIconMaterial"] {font-size:18px !important;height:18px !important;line-height:18px !important;width:18px !important;flex:0 0 18px;}
section[data-testid="stSidebar"]:has([class*="-children"] button[kind="primary"]) [class*="st-key-sidebar-disclosure-"][class*="-open"] [data-testid="stButton"] button[kind="primary"] {background:var(--sidebar-panel) !important;font-weight:500 !important;}
section[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] * {color:var(--sidebar-gold-text) !important;-webkit-text-fill-color:var(--sidebar-gold-text) !important;}
section[data-testid="stSidebar"] [data-testid="stButton"] button > div {min-width:0;}
section[data-testid="stSidebar"] [data-testid="stButton"] button:has(.sc-orders-action-badge) {padding-right:52px !important;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"] button:has(.sc-orders-action-badge) {padding-right:72px !important;}
section[data-testid="stSidebar"] [data-testid="stButton"] button:active {background:var(--sidebar-panel-hover) !important;}
/* Shared disclosure treatment, including all current and future sidebar families. */
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"] {background:transparent;border-radius:7px;padding:0;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"][class*="-open"] {background:rgba(255,255,255,.025);border-radius:7px 7px 0 0;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"] button {padding-right:30px !important;position:relative;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"] button::after {content:"";position:absolute;right:14px;top:calc(50% - 4px);width:5px;height:5px;border-bottom:1.4px solid var(--sidebar-muted);border-right:1.4px solid var(--sidebar-muted);transform:rotate(45deg);transition:transform 150ms ease;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-"][class*="-open"] button::after {transform:rotate(225deg);top:calc(50% - 1px);}
section[data-testid="stSidebar"] [class*="st-key-sidebar-"][class*="-children"] {background:rgba(255,255,255,.025);border-radius:0 0 7px 7px;box-sizing:border-box;margin:-2px 0 4px;padding:0 0 6px;width:100%;max-width:100%;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-"][class*="-children"] [data-testid="stButton"] button {height:auto;min-height:33px;border-radius:0 !important;padding-left:36px !important;font-weight:500 !important;}
section[data-testid="stSidebar"] [class*="st-key-sidebar-"][class*="-children"] [data-testid="stButton"] button[kind="primary"] {font-weight:600 !important;}
section[data-testid="stSidebar"] .st-key-sidebar-profile-footer {background:var(--sidebar-bg-bottom);margin-top:10px;padding-bottom:6px;}
section[data-testid="stSidebar"] .st-key-sidebar-profile-footer [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] .sc-sidebar-role {color:var(--sidebar-muted) !important;font-size:12px;}
section[data-testid="stSidebar"] hr {border-color:var(--sidebar-border);margin:12px 0 8px;}
section[data-testid="stSidebar"] h3 {font-size:14px;color:var(--sidebar-text);}
section[data-testid="stSidebar"] .sc-files-window-launcher-fallback {display:block;padding:11px 12px;color:var(--sidebar-text) !important;text-decoration:none;}
section[data-testid="stSidebar"] .sc-files-window-launcher-fallback:hover {background:var(--sidebar-panel-hover);border-radius:7px;}
@media (pointer:coarse), (max-width:820px) {
 section[data-testid="stSidebar"] [data-testid="stButton"] button {min-height:44px;}
}
"""
