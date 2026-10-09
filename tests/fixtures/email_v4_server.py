"""Release-style local ASGI fixture; allowlisted fabricated workspaces only."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from streamlit.web.server.starlette import App
campaign=os.getenv('EMAIL_V4_CAMPAIGNS')=='1'
uvicorn.run(App(str(Path(__file__).with_name('crm_email_performance.py' if campaign else 'crm_automation_preview.py'))),host='127.0.0.1',port=8543 if campaign else 8533)
