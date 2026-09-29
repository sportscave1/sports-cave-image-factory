"""App-wide, event-driven recovery for Streamlit's connection-error state."""
from pathlib import Path


def install(st):
    script=(Path(__file__).parent/'components'/'session_recovery.js').read_text(encoding='utf-8')
    st.html('<script>'+script+'</script>',unsafe_allow_javascript=True)
