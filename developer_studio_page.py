"""Lazy owner-only browser surface. No local filesystem or Docker server API."""
from pathlib import Path
import json


STUDIO_ASSETS = ("workspace.js", "workspace.css", "editor.js", "code-editor.js", "editor.css")


def panel_html():
    assets = Path(__file__).parent / "components" / "developer_studio"
    local_assets=Path(__file__).parent/"scripts"/"studio"/"ui"
    bundle=json.dumps({name:local_assets.joinpath(name).read_text(encoding="utf-8-sig") for name in STUDIO_ASSETS}).replace("</", "<\\/")
    return (assets.joinpath("panel.html").read_text(encoding="utf-8")
            .replace("/*STUDIO_CSS*/", assets.joinpath("panel.css").read_text(encoding="utf-8"))
            .replace("/*STUDIO_JS*/", assets.joinpath("panel.js").read_text(encoding="utf-8"))
            .replace("/*STUDIO_V6_BUNDLE*/",bundle))


def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_reporting_owner(user):
        st.error("Dev Mode is available only to the configured owner.")
        return
    from streamlit.components.v1 import html
    st.html("""<style>
    .sc-dev-mode-entry {display:block;color:#ddd6bc;text-decoration:none;padding:10px 12px;font:600 14px "Segoe UI",sans-serif;border-radius:6px;}
    [data-testid="stAppViewContainer"]:has(.st-key-developer-studio-workspace) [data-testid="stSidebar"],
    [data-testid="stAppViewContainer"]:has(.st-key-developer-studio-workspace) .sc-topbar,
    [data-testid="stAppViewContainer"]:has(.st-key-developer-studio-workspace) [data-testid="stHeader"] {display:none !important;}
    body:has(.st-key-developer-studio-workspace) #sports-cave-os-top-bar,
    body:has(.st-key-developer-studio-workspace) #sports-cave-navigation-loader,
    body:has(.st-key-developer-studio-workspace) iframe[data-sc-top-bar] {display:none !important;}
    body:has(.st-key-developer-studio-workspace) {--sc-topbar-height:0px !important;}

    [data-testid="stMain"]:has(.st-key-developer-studio-workspace) {overflow:hidden !important;}
    [data-testid="stMainBlockContainer"]:has(.st-key-developer-studio-workspace) {
        max-width:none !important; width:100% !important;
        padding:0 !important;
    }
    [data-testid="stMainBlockContainer"]:has(.st-key-developer-studio-workspace) > [data-testid="stVerticalBlock"] {gap:0 !important;}
    .st-key-developer-studio-workspace iframe {
        display:block; width:100%; height:100dvh !important;
    }
    </style>""")
    with st.container(key="developer-studio-workspace"):
        html(panel_html(), height=790, scrolling=False)
