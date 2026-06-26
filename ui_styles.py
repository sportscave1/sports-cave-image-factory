import html

import streamlit as st


def inject_global_ui_styles():
    st.markdown(
        """
        <style>
        :root {
            --sc-bg: #090909;
            --sc-panel: #11100e;
            --sc-panel-soft: #171512;
            --sc-border: rgba(213, 170, 86, 0.28);
            --sc-gold: #d9ad55;
            --sc-gold-dark: #9a6d22;
            --sc-cream: #f7f2e9;
            --sc-text: #f4eee5;
            --sc-muted: #aaa196;
            --sc-dark-text: #191713;
            --sc-red: #b4232a;
            --sc-green: #1f7a4d;
        }
        .sc-page-header {
            border: 1px solid var(--sc-border);
            background: linear-gradient(135deg, #0d0c0a 0%, #17130c 72%, #21190b 100%);
            border-radius: 8px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }
        .sc-page-header h1 {
            color: var(--sc-text);
            font-size: 1.65rem;
            line-height: 1.1;
            margin: 0 0 5px 0;
            letter-spacing: 0;
        }
        .sc-page-header p {
            color: var(--sc-muted);
            font-size: 0.92rem;
            margin: 0;
        }
        .sc-section-title {
            color: var(--sc-text);
            font-size: 1rem;
            font-weight: 750;
            margin: 12px 0 6px 0;
        }
        .sc-source-banner {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: #111;
            border-radius: 8px;
            padding: 8px 10px;
            margin: 8px 0 10px 0;
            color: var(--sc-text);
            font-size: 0.86rem;
        }
        .sc-source-item {
            color: var(--sc-muted);
        }
        .sc-source-item strong {
            color: var(--sc-text);
        }
        .sc-metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(126px, 1fr));
            gap: 8px;
            margin: 8px 0 10px 0;
        }
        .sc-metric-card {
            min-height: 58px;
            border: 1px solid #ded4c4;
            background: var(--sc-cream);
            border-radius: 8px;
            padding: 8px 10px;
            color: var(--sc-dark-text);
        }
        .sc-metric-label {
            color: #665d50;
            font-size: 0.72rem;
            font-weight: 750;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 3px;
        }
        .sc-metric-value {
            color: var(--sc-dark-text);
            font-size: 1.15rem;
            line-height: 1.1;
            font-weight: 800;
        }
        .sc-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 4px 0 8px 0;
        }
        .sc-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 3px 8px;
            font-size: 0.78rem;
            font-weight: 750;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: #1c1a17;
            color: var(--sc-text);
        }
        .sc-pill.good {
            background: rgba(31, 122, 77, 0.18);
            border-color: rgba(31, 122, 77, 0.45);
            color: #c8f2dc;
        }
        .sc-pill.warn {
            background: rgba(217, 173, 85, 0.16);
            border-color: rgba(217, 173, 85, 0.45);
            color: #ffe2a3;
        }
        .sc-pill.danger {
            background: rgba(180, 35, 42, 0.2);
            border-color: rgba(180, 35, 42, 0.55);
            color: #ffd3d5;
        }
        .sc-empty {
            border: 1px dashed rgba(255, 255, 255, 0.18);
            background: #111;
            color: var(--sc-muted);
            border-radius: 8px;
            padding: 14px;
            font-size: 0.92rem;
        }
        .sc-table-frame {
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: #101010;
            border-radius: 8px;
            padding: 8px;
            margin-top: 8px;
        }
        div.stButton > button,
        div.stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] button {
            border-radius: 7px !important;
            min-height: 38px !important;
            font-weight: 750 !important;
            border: 1px solid var(--sc-border) !important;
            background: var(--sc-cream) !important;
            color: var(--sc-dark-text) !important;
        }
        div.stButton > button:hover,
        div.stButton > button:focus,
        div.stButton > button:active,
        div.stDownloadButton > button:hover,
        div.stDownloadButton > button:focus,
        div.stDownloadButton > button:active,
        div[data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stFormSubmitButton"] button:focus,
        div[data-testid="stFormSubmitButton"] button:active {
            background: #efe4d2 !important;
            color: var(--sc-dark-text) !important;
            border-color: var(--sc-gold-dark) !important;
            box-shadow: none !important;
        }
        div.stButton > button[kind="primary"] {
            background: var(--sc-gold) !important;
            color: #111 !important;
            border-color: var(--sc-gold) !important;
        }
        div.stButton > button:disabled,
        div.stDownloadButton > button:disabled {
            background: #2a2927 !important;
            color: #9e978d !important;
            border-color: rgba(255,255,255,0.12) !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            border-bottom: 1px solid rgba(255,255,255,0.12);
        }
        .stTabs [data-baseweb="tab"] {
            height: 36px;
            color: var(--sc-muted);
            font-weight: 750;
            padding: 6px 10px;
        }
        .stTabs [aria-selected="true"] {
            color: var(--sc-text) !important;
            border-bottom-color: var(--sc-gold) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title, subtitle):
    st.markdown(
        f"""
        <div class="sc-page-header">
            <h1>{html.escape(str(title))}</h1>
            <p>{html.escape(str(subtitle))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title):
    st.markdown(f'<div class="sc-section-title">{html.escape(str(title))}</div>', unsafe_allow_html=True)


def metric_strip(metrics):
    cards = []
    for label, value in metrics:
        cards.append(
            f"""
            <div class="sc-metric-card">
                <div class="sc-metric-label">{html.escape(str(label))}</div>
                <div class="sc-metric-value">{html.escape(str(value))}</div>
            </div>
            """
        )
    st.markdown(f'<div class="sc-metric-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def status_pills(items):
    pills = []
    for label, tone in items:
        safe_tone = tone if tone in {"good", "warn", "danger"} else ""
        pills.append(f'<span class="sc-pill {safe_tone}">{html.escape(str(label))}</span>')
    st.markdown(f'<div class="sc-pill-row">{"".join(pills)}</div>', unsafe_allow_html=True)


def source_status_banner(items):
    parts = []
    for label, value in items:
        parts.append(
            f'<span class="sc-source-item">{html.escape(str(label))}: <strong>{html.escape(str(value))}</strong></span>'
        )
    st.markdown(f'<div class="sc-source-banner">{"".join(parts)}</div>', unsafe_allow_html=True)


def empty_state(message):
    st.markdown(f'<div class="sc-empty">{html.escape(str(message))}</div>', unsafe_allow_html=True)


def table_frame_start():
    st.markdown('<div class="sc-table-frame">', unsafe_allow_html=True)


def table_frame_end():
    st.markdown("</div>", unsafe_allow_html=True)
