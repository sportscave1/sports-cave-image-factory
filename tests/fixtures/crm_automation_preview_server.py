"""Release-style ASGI smoke fixture: no frontend dev server or production APIs."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from streamlit.web.server.starlette import App
uvicorn.run(App(str(Path(__file__).with_name('crm_automation_preview.py'))),host='127.0.0.1',port=8533)
