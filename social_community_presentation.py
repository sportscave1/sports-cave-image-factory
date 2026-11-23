"""Small, escaped presentation helpers shared by the four community views."""
import html
from pathlib import Path

import streamlit as st

CSS = Path(__file__).with_name("social_community.css").read_text(encoding="utf-8")


def inject():
    st.markdown("<style>" + CSS + "</style>", unsafe_allow_html=True)


def detail_header(name, subtitle, status="", tone="neutral"):
    name, subtitle, status = (html.escape(str(value or "")) for value in (name, subtitle, status))
    initials = html.escape("".join(word[0] for word in html.unescape(name).lstrip("@").split()[:2]).upper() or "SC")
    tone = tone if tone in ("neutral", "gold", "green", "blue") else "neutral"
    st.markdown('<div class="sc-detail-header"><span class="sc-avatar">' + initials +
                '</span><div class="sc-detail-person"><strong>' + name + '</strong><small>' + subtitle +
                '</small></div>' + ('<span class="sc-badge ' + tone + '">' + status + '</span>' if status else '') +
                '</div>', unsafe_allow_html=True)


def empty_state(title, description):
    st.markdown('<div class="sc-empty"><span class="sc-empty-icon" aria-hidden="true">◇</span><strong>' +
                html.escape(title) + '</strong><p>' + html.escape(description) + '</p></div>', unsafe_allow_html=True)


def facts(title, rows):
    content = ''.join('<div class="sc-fact"><span>' + html.escape(str(label)) + '</span><strong>' +
                      html.escape(str(value)) + '</strong></div>' for label, value in rows)
    st.markdown('<section class="sc-facts"><h3>' + html.escape(title) + '</h3>' + content + '</section>', unsafe_allow_html=True)
