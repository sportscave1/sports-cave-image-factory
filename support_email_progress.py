"""Transient send-stage bridge; no transport, credentials or message content."""
import json

import streamlit.components.v1 as components


def progress_callback(slot, operation_id):
    def update(percent, label):
        payload = json.dumps({"type": "sc:send-progress", "operation_id": operation_id,
                              "percent": percent, "label": label}).replace("</", "<\\/")
        with slot:
            components.html('<script>const message=' + payload + ';'
                'window.frameElement.dataset.scSendProgress=message.operation_id;'
                'for(const frame of window.parent.document.querySelectorAll("iframe")) {'
                'if(frame.title==="support_email_page.support_email_desktop")'
                'frame.contentWindow.postMessage(message,window.parent.location.origin);}'
                '</script>', height=0)
    return update
