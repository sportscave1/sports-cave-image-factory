"""App-wide, event-driven recovery for Streamlit's connection-error state."""
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _source():
    return (Path(__file__).parent/'components'/'session_recovery.js').read_text(encoding='utf-8')


def install(st):
    st.html('<script>'+_source()+'</script>',unsafe_allow_javascript=True)
