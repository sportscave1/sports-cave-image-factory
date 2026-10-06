"""Shared, route-scoped Social Media layout; no provider or database calls."""
import streamlit as st

def inject_styles():
    st.html("""<style>
    [data-testid="stMainBlockContainer"]:has(.sc-social-shell){padding:calc(var(--sc-topbar-height,64px) + 20px) 24px 32px;max-width:100%}
    [data-testid="stMainBlockContainer"]:has(.sc-social-shell)>[data-testid="stVerticalBlock"]{gap:.6rem}
    [data-testid="stMainBlockContainer"]:has(.sc-social-shell) [data-testid="stElementContainer"]:has(iframe[height="0"]){display:none}
    [data-testid="stMainBlockContainer"]:has(.sc-social-shell) [data-testid="stElementContainer"]:has(.sc-social-shell){display:none}
    [data-testid="stMainBlockContainer"]:has(.sc-social-shell) [data-testid="stVerticalBlock"]{gap:.5rem}
    .sc-social-shell{height:0}
    .sc-social-header{background:transparent!important;color:#171717!important;border:0!important;padding:0!important;margin:0 0 .4rem!important;box-shadow:none!important}
    .sc-social-header h1{color:#171717!important;font-size:1.5rem!important;margin:0!important;padding:0!important}
    .sc-social-header p{color:#77716a!important;margin:.25rem 0!important}
    .sc-social-profiles{margin-bottom:.4rem!important;gap:.4rem!important}
    .sc-social-profiles a{min-height:40px!important;padding:.35rem .6rem!important}
    .sc-social-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:4px 0}
    .sc-social-kpi{border:1px solid #e4ded4;border-top:2px solid #b79b60;border-radius:8px;padding:10px 12px;background:#faf8f4}
    .sc-social-kpi span{display:block;font-size:12px;color:#736e66}.sc-social-kpi strong{font-size:23px;color:#171717}
    @media(max-width:760px){[data-testid="stMainBlockContainer"]:has(.sc-social-shell){padding:calc(var(--sc-topbar-height,56px) + 14px) 14px 24px}.sc-social-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.sc-social-profiles{grid-template-columns:repeat(3,minmax(0,1fr))!important}
    .st-key-wp-analytics-filters [data-testid="stHorizontalBlock"],.st-key-wp-inbox-filters [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
    .st-key-wp-analytics-filters [data-testid="stColumn"],.st-key-wp-inbox-filters [data-testid="stColumn"]{flex:1 1 calc(50% - 8px);min-width:0;width:calc(50% - 8px)}}
    </style>""")
    st.markdown('<div class="sc-social-shell"></div>',unsafe_allow_html=True)
