"""Rerun-safe temporary UI feedback shared by Sports Cave OS pages."""

import hashlib
import json


TEMPORARY_TOAST_MS = 3000


def temporary_toast_html(message, *, event_key=""):
    """Return a parent-shell toast that expires once, even across iframe remounts."""

    clean_message = str(message or "").strip()
    identity = str(event_key or "").strip()
    if not identity:
        identity = hashlib.sha1(clean_message.encode("utf-8")).hexdigest()
    return f"""
<script>
(() => {{
  const parentWindow = window.parent || window;
  const doc = parentWindow.document;
  const identity = {json.dumps(identity)};
  const message = {json.dumps(clean_message)};
  const durationMs = {TEMPORARY_TOAST_MS};
  const rootId = "sports-cave-temporary-toast";
  const styleId = "sports-cave-temporary-toast-style";
  let style = doc.getElementById(styleId);
  if (!style) {{
    style = doc.createElement("style");
    style.id = styleId;
    style.textContent = `
      #${{rootId}} {{
        background:#171715;border:1px solid #b79243;border-radius:7px;
        bottom:22px;box-shadow:0 12px 32px rgba(0,0,0,.24);color:#fff;
        font:700 14px/1.35 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;
        max-width:min(420px,calc(100vw - 32px));padding:10px 14px;
        position:fixed;right:22px;z-index:999999;
      }}
      #${{rootId}}[hidden] {{ display:none !important; }}
      @media (max-width:680px) {{ #${{rootId}} {{ bottom:14px;left:16px;right:16px; }} }}
    `;
    doc.head.appendChild(style);
  }}
  let root = doc.getElementById(rootId);
  if (!root) {{
    root = doc.createElement("div");
    root.id = rootId;
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");
    root.setAttribute("aria-atomic", "true");
    root.hidden = true;
    doc.body.appendChild(root);
  }}
  const runtime = parentWindow.SportsCaveTransientToast || {{
    current: null,
    dismiss() {{
      if (this.current?.timer) parentWindow.clearTimeout(this.current.timer);
      const liveRoot = doc.getElementById(rootId);
      if (liveRoot) {{
        liveRoot.hidden = true;
        liveRoot.replaceChildren();
        liveRoot.removeAttribute("data-toast-identity");
      }}
      this.current = null;
    }},
    show(nextRoot, nextIdentity, nextMessage) {{
      const now = Date.now();
      if (this.current?.identity === nextIdentity && this.current.expiresAt > now) return false;
      this.dismiss();
      nextRoot.textContent = nextMessage;
      nextRoot.dataset.toastIdentity = nextIdentity;
      nextRoot.hidden = false;
      const current = {{identity: nextIdentity, expiresAt: Date.now() + durationMs, timer: null}};
      current.timer = parentWindow.setTimeout(() => this.dismiss(), durationMs);
      this.current = current;
      return true;
    }},
  }};
  parentWindow.SportsCaveTransientToast = runtime;
  runtime.show(root, identity, message);
}})();
</script>
"""


def show_temporary_toast(components_module, message, *, event_key=""):
    """Mount a zero-height bridge to the persistent parent toast runtime."""

    if not str(message or "").strip():
        return
    components_module.html(
        temporary_toast_html(message, event_key=event_key),
        height=0,
        width=0,
    )
