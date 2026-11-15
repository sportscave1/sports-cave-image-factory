"""Attach compact local controls to the existing Automation text inputs."""
import json
from pathlib import Path
import uuid
import streamlit as st

SCRIPT=Path(__file__).with_name('components').joinpath('crm_sections/personalise.js').read_text(encoding='utf8')


def controls(key):
    st.html('''<style>
    .sc-personalise-trigger{position:absolute;right:0;top:-2px;background:transparent;border:0;color:#72571e;font:12px system-ui;cursor:pointer;padding:2px 5px;border-radius:4px}
    .sc-personalise-trigger:focus-visible,.sc-personalise-menu button:focus-visible{outline:2px solid #aa873b}
    .sc-personalise-menu{position:fixed;margin:0;padding:4px;width:202px;border:1px solid #d8d5cc;border-radius:5px;background:#fffefa;box-shadow:0 2px 6px #0001}
    .sc-personalise-menu button{display:block;width:100%;text-align:left;background:none;border:0;padding:7px 9px;color:#242424;font:13px system-ui;cursor:pointer;border-radius:3px}
    .sc-personalise-menu button:hover{background:#f1ede3}
    </style><script>/*'''+uuid.uuid4().hex+'*/'+SCRIPT+'window.scInstallPersonalisation('+json.dumps([key+'subject',key+'preheader'])+');</script>',unsafe_allow_javascript=True)
