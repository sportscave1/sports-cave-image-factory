"""Small browser-only clipboard control; copies the complete current text."""
import json


def copy_html(text):
    payload = json.dumps(text).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return """<style>body{margin:0;font:15px system-ui}button{background:#d6a548;color:#18140c;border:0;border-radius:8px;padding:12px 22px;font:600 15px system-ui;cursor:pointer}button:focus-visible{outline:3px solid #866018;outline-offset:2px}#status{margin-left:12px;font-size:14px}</style>
<button id="copy" type="button">Copy full prompt</button><span id="status" role="status" aria-live="polite"></span>
<script>
const text = """ + payload + """;
const button = document.getElementById('copy');
const status = document.getElementById('status');
function fallback() {
  const field = document.createElement('textarea');
  field.value = text;
  field.style.cssText = 'position:fixed;left:-9999px;top:0';
  document.body.appendChild(field);
  field.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (_) {}
  field.remove();
  button.focus();
  return copied;
}
button.onclick = async () => {
  let copied = false;
  try { await navigator.clipboard.writeText(text); copied = true; }
  catch (_) { copied = fallback(); }
  status.textContent = copied ? 'Copied!' : 'Open the preview below and use its copy icon.';
};
</script>"""


def render_copy(st, text, *, preview_label='Show full prompt'):
    import streamlit.components.v1 as components
    components.html(copy_html(text), height=62)
    with st.expander(preview_label, expanded=False):
        st.code(text, language=None, wrap_lines=True)
