# Orders parallel fragment layout fix

User authorized diagnosing, fixing and publishing the Orders failure on
24 November 2026. Task 20261124-a55b7bbe, owner
codex-orders-layout-fix-20261124-session-a.

## Cause and fix

The performance change made the Orders workspace a parallel fragment. Both
Orders CSS calls used style-only st.html output. Streamlit routes that output
to its global event container, outside the fragment, causing
StreamlitInvalidLayoutContextError on initial page load. The mobile refunded
card styles had the same problem. See the
[Streamlit st.html documentation](https://docs.streamlit.io/develop/api-reference/text/st.html).

Both CSS calls now use st.markdown with trusted local style markup, so their
deltas belong to the active fragment. The CSS is unchanged; its existing rule
hides style-only Markdown containers, leaving no blank layout slot.

Parallel rendering, progressive completion, retained rows, scoped loading and
permission checks remain unchanged. No SQL, pooling, compression, auth or
business actions changed.

## Regression coverage

Two new tests execute the actual desktop style function and actual refunded
mobile-card renderer inside a real parallel Streamlit fragment, with synthetic
resources and no business app/provider imports. Both fail on deployed code
with the layout ownership exception and pass with this fix.

The previous browser measurement fixture stubbed out the style function.
It now executes the actual Orders CSS function. The browser checks initial
load, search fragment reruns, 150 synthetic units, retained rows, desktop and
390px layout, and departure during a pending read. It asserts the CSS remains
fragment-owned, occupies zero height, and applies the original desktop/mobile
padding (72px/78px). Completion/search cause no extra full-app reruns.

Local focused suite: 104 passed and 16 subtests. Native Orders feed/grid
JavaScript: 14 passed; shell request/state checks passed.

~~~powershell
python -m pytest -q tests/test_orders_fragment_styles.py
python scripts/benchmark_page_loading.py --samples 1 --out .tmp-orders-layout/pages.json
~~~

The isolated slow-Orders browser sample (1.4s synthetic read) completed in
1.877s, preserving the progressive-loading behavior. This is not an
authenticated production timing.

OS performance CI now includes both layout tests and the real CSS browser
path. Final commit, CI and live deployment verification are recorded in the
release receipt after deployment. No production data is used in fixtures.
