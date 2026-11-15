"""Streamed Inbox/Automations placeholders and shared Email stage timings."""
from contextlib import contextmanager
import logging
import time

import streamlit as st

LOGGER = logging.getLogger(__name__)


@contextmanager
def stage(page, name):
    started = time.perf_counter()
    try:
        yield
    finally:
        LOGGER.info('email_load page=%s stage=%s duration_ms=%.1f', page, name,
                    (time.perf_counter() - started) * 1000)


def shell(page):
    """Emit before remote reads. No clients, queries, scripts or persisted state."""
    slot = st.empty()
    controls = {'Inbox': '+ New mail　　Search mail　　Refresh',
                'Automations': 'Flow　　Email　　Refresh'}[page]
    sidebar = ('<aside>Inbox<br>Drafts<br>Sent<br>Archive<br>Junk<br>Trash<br>Flagged</aside>'
               if page == 'Inbox' else '')
    slot.html('''<style>
    .sc-email-loading{color:#242320;background:#faf9f6;padding:16px;min-height:380px}
    .sc-email-loading header{display:flex;gap:24px;align-items:center;flex-wrap:wrap;
        border-bottom:1px solid #e7e3da;padding-bottom:16px}
    .sc-email-loading header span{color:#77736b;font-size:14px}
    .sc-email-loading main{display:flex;gap:24px;padding-top:20px}
    .sc-email-loading aside{min-width:110px;line-height:36px;font-size:14px}
    .sc-email-loading section{flex:1;min-width:0}
    .sc-email-loading p{height:16px;max-width:620px;background:#eeece6;border-radius:3px;margin:14px 0}
    </style><div class="sc-email-loading" role="status" aria-label="Loading ''' + page + '''">
    <header><strong>EMAIL · ''' + page.upper() + '''</strong><span>''' + controls + '''</span></header>
    <main>''' + sidebar + '''<section><p></p><p></p><p></p></section></main></div>''')
    LOGGER.info('email_load page=%s stage=shell_emitted', page)
    return slot
