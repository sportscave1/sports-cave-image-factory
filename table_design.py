"""Sports Cave table presentation tokens; no data or widget-state transformations.

Native grids use TABLE_ROW_HEIGHT and Streamlit's dataframe-only theme options.
HTML hosts embed TABLE_CSS at build time (scripts/sync_table_design.py) so isolated
component frames need no runtime fetch, observers, timers, or new dependencies.
"""

TABLE_ROW_HEIGHT = 34

TABLE_CSS = """
/* Sports Cave OS tables V3. Explicit table scopes only. */
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stDataFrame"], [data-testid="stTable"],
    html[data-sc-table-host] .table-wrap, html[data-sc-table-host="checkout"] .wrap,
    html[data-sc-table-host] .view-details, html[data-sc-table-host] .view-list,
    html[data-sc-table-host] .details-header, html[data-sc-table-host="uploads"] .uploads,
    html[data-sc-table-host="planner"] .task-row, html[data-sc-table-host="planner"] .task-header,
    html[data-sc-table-host="planner"] .tactic-row) {
  --sc-table-paper: #fffefa;
  --sc-table-head: #f3f2ec;
  --sc-table-line: #eeece5;
  --sc-table-border: #e4e2da;
  --sc-table-hover: #f7f5ef;
  --sc-table-selected: #eee7d7;
  --sc-table-ink: #30332e;
  --sc-table-muted: #64665f;
  --sc-table-focus: #9a7937;
  scrollbar-color: #c8c5bb transparent;
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    html[data-sc-table-host] .table-wrap, html[data-sc-table-host="checkout"] .wrap) {
  max-width: 100%; overflow: auto; border: 1px solid var(--sc-table-border);
  border-radius: 5px; background: var(--sc-table-paper);
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  font-family: inherit; font-size: 13px; color: var(--sc-table-ink);
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) :is(td, th) {
  box-sizing: border-box; height: 34px; padding: 6px 10px;
  border: 0; border-bottom: 1px solid var(--sc-table-line);
  vertical-align: middle; line-height: 20px;
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) th {
  background: var(--sc-table-head); color: var(--sc-table-muted);
  font-size: 12px; font-weight: 600; text-transform: none;
  text-align: left; border-bottom-color: var(--sc-table-border);
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    html[data-sc-table-host] .table-wrap) th { position: sticky; top: 0; z-index: 1; }
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) td { background: var(--sc-table-paper); }
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) tbody tr:hover td { background: var(--sc-table-hover); }
:is(.sc-table, html[data-sc-table-host="checkout"] .wrap) tr:has(input[type="checkbox"]:checked) td {
  background: var(--sc-table-selected);
}
:is(.sc-table, .sc-activity-table-wrap, .prodigi-reference-scroll,
    [data-testid="stTable"], html[data-sc-table-host] .table-wrap,
    html[data-sc-table-host="checkout"] .wrap) :is(button, a, input, select):focus-visible {
  outline: 2px solid var(--sc-table-focus); outline-offset: 2px;
}
.sc-table .sc-table-number { text-align: right; font-variant-numeric: tabular-nums; }
.sc-table .sc-table-action { min-height: 28px; padding: 3px 8px; font: inherit; }
.sc-table .sc-table-success { color: #28633e; }
.sc-table .sc-table-pending { color: #826222; }
.sc-table .sc-table-error { color: #a13a32; }
.sc-table .sc-table-neutral { color: #64665f; }
[data-testid="stDataFrame"] { border-radius: 5px; }
[data-testid="stTable"] { max-width: 100%; overflow-x: auto; }
/* Preserve checkout frozen-column geometry and its focus/scroll implementation. */
html[data-sc-table-host="checkout"] .wrap :is(td, th):first-child { padding: 4px 6px; }
@media (max-width: 600px) {
  html[data-sc-table-host="checkout"] .wrap :is(td, th) { padding: 6px 8px; }
  html[data-sc-table-host="checkout"] .wrap :is(td, th):first-child { padding: 4px 6px; }
}
/* Planner inputs/timers retain their natural multiline row height. */
html[data-sc-table-host="planner"] .table-wrap table { min-width: max-content; }
html[data-sc-table-host="planner"] .table-wrap td { font-size: 13px; }
html[data-sc-table-host="planner"] :is(.task-row, .tactic-row) {
  border: 0; border-bottom: 1px solid var(--sc-table-line); border-radius: 0;
  margin-bottom: 0; background: var(--sc-table-paper);
}
html[data-sc-table-host="planner"] .task-header {
  background: var(--sc-table-head); color: var(--sc-table-muted);
  min-height: 34px; align-items: center; font-size: 12px; font-weight: 600; text-transform: none;
}
html[data-sc-table-host="planner"] :is(.task-row, .tactic-row):hover { background: var(--sc-table-hover); }
/* File manager Details/List only; thumbnail/icon views are not data tables. */
html[data-sc-table-host="files"] .details-header {
  background: var(--sc-table-head); color: var(--sc-table-muted); border-color: var(--sc-table-border);
  font-weight: 600;
}
html[data-sc-table-host="files"] .details-header > span { border-right: 0; }
html[data-sc-table-host="files"] :is(.view-details, .view-list) .file-item {
  background: var(--sc-table-paper); border-bottom: 1px solid var(--sc-table-line);
  min-height: 38px; border-radius: 0;
}
html[data-sc-table-host="files"] .view-details .detail-modified { line-height: 38px; }
html[data-sc-table-host="files"] :is(.view-details, .view-list) .file-item:hover { background: var(--sc-table-hover); }
html[data-sc-table-host="files"] :is(.view-details, .view-list) .file-item.selected { background: var(--sc-table-selected); }
html[data-sc-table-host="uploads"] .upload-row { background: var(--sc-table-paper); border-bottom-color: var(--sc-table-line); }
html[data-sc-table-host="uploads"] .upload-row:hover { background: var(--sc-table-hover); }
html[data-sc-table-host="uploads"] .upload-row .cell { border-right: 0; }
"""


def inject_table_styles(st):
    """Call once from the app's existing style injection, without wrapping widgets."""
    st.markdown("<style>" + TABLE_CSS + "</style>", unsafe_allow_html=True)
