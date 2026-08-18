"""Shared, text-free loading indicator for ordinary Sports Cave OS reads."""

from contextlib import contextmanager

import streamlit as st


SPINNER_ONLY_CSS = """
<style>
.sc-loading-only {
    align-items: center;
    display: flex;
    justify-content: center;
    min-height: 72px;
    width: 100%;
}
.sc-loading-only.sc-loading-only--compact { min-height: 34px; }
.sc-loading-spinner {
    animation: sc-loading-spin 0.72s linear infinite;
    border: 2px solid rgba(183, 146, 67, 0.24);
    border-radius: 50%;
    border-top-color: #b79243;
    box-sizing: border-box;
    display: inline-block;
    height: 22px;
    width: 22px;
}
@keyframes sc-loading-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
    .sc-loading-spinner { animation: none; }
}
</style>
"""


def spinner_html(*, compact=False):
    modifier = " sc-loading-only--compact" if compact else ""
    return (
        SPINNER_ONLY_CSS
        + f'<div class="sc-loading-only{modifier}" role="status" aria-label="Loading">'
        '<span class="sc-loading-spinner" aria-hidden="true"></span>'
        "</div>"
    )


def render_spinner(target=st, *, compact=False):
    """Render one centred spinner with no visible loading copy."""

    target.markdown(spinner_html(compact=compact), unsafe_allow_html=True)


@contextmanager
def spinner_only(target=st, *, compact=False):
    """Show a spinner only for the lifetime of an ordinary blocking read."""

    placeholder = target.empty()
    placeholder.markdown(spinner_html(compact=compact), unsafe_allow_html=True)
    try:
        yield
    finally:
        placeholder.empty()
