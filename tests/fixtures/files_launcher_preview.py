"""Production-path Files launcher fixture; no data/storage connections.

Run with Python --serve. Deliberately declare before ScriptRunContext to reproduce
the old registration cache defect, then serve the real component via Starlette.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import files_window_launcher
import streamlit.components.v1 as components

if '--serve' in sys.argv:
    sys.argv.remove('--serve')
    import uvicorn
    from streamlit.web.server.starlette import App
    from starlette.routing import Route
    from starlette.responses import HTMLResponse

    files_window_launcher.get_component(components)  # No session yet, intentionally.

    async def destination(request):
        return HTMLResponse('<h1>Sports Cave Files</h1><p>Local launcher destination verified. '
                            'No file records or external storage accessed.</p>')

    uvicorn.run(App(str(Path(__file__).resolve()), routes=[Route('/files-window', destination)]),
                host='127.0.0.1', port=8505)
else:
    import streamlit as st

    st.set_page_config(page_title='Files launcher · production assets fixture', layout='wide')
    with st.sidebar:
        with st.container(key='files-window-launcher-slot'):
            files_window_launcher.render(st, components)
        st.button('Reporting')
        st.button('Accounts & Access')
    st.title('Files launcher deployment verification')
    st.caption('Production bundled assets; intentionally prewarmed outside a session. No external I/O.')
    st.button('Rerun fixture')
