"""Lazy owner-only browser surface. No local filesystem or Docker server API."""
from pathlib import Path


def panel_html():
    assets = Path(__file__).parent / "components" / "developer_studio"
    return (assets.joinpath("panel.html").read_text(encoding="utf-8")
            .replace("/*STUDIO_CSS*/", assets.joinpath("panel.css").read_text(encoding="utf-8"))
            .replace("/*STUDIO_JS*/", assets.joinpath("panel.js").read_text(encoding="utf-8")))


def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_reporting_owner(user):
        st.error("Developer Studio is available only to the configured owner.")
        return
    from streamlit.components.v1 import html
    html(panel_html(), height=650, scrolling=True)
