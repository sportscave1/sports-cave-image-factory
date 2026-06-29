"""Compatibility entrypoint for the standalone webhook service.

The main Sports Cave OS UI runs direct Streamlit from render.yaml. This module
is kept so accidental `python server.py` starts the webhook-only service instead
of trying to proxy Streamlit.
"""

import os

import uvicorn

from webhook_server import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8500")))
