from table_design import TABLE_ROW_HEIGHT
from sports_categories import normalize_sport_category, normalize_sport_state
from datetime import datetime, timezone
import hashlib
import html

import streamlit as st
import streamlit.components.v1 as components

import design_studio_styles
import sports_cave_dashboard
import ui_feedback
from ui_option_ordering import alphabetize_options, selected_option_index


SELECTED_DESIGN_TASK_KEY = "design-studio-v2-selected-task"
LOADED_DESIGN_TASK_KEY = "design-studio-v2-loaded-task"
SCHEDULE_VIEW_KEY = "design-schedule-view"
SCHEDULE_ACTIVE_COUNT_KEY = "design-schedule-active-count"
SCHEDULE_GENERATOR_OPEN_KEY = "design-schedule-generator-open"
SCHEDULE_IMPORT_OPEN_KEY = "design-schedule-import-open"
SCHEDULE_EXPORT_OPEN_KEY = "design-schedule-export-open"
SCHEDULE_ADD_OPEN_KEY = "design-schedule-add-open"
SCHEDULE_IMPORT_PREVIEW_KEY = "design-schedule-import-preview"
SCHEDULE_IMPORT_NONCE_KEY = "design-schedule-import-nonce"
SCHEDULE_TOAST_KEY = "design-schedule-toast"
SCHEDULE_DETAILS_TASK_KEY = "design-schedule-details-task-id"
SCHEDULE_COMPLETE_TASK_KEY = "design-schedule-complete-task-id"
SCHEDULE_DELETE_TASK_KEY = "design-schedule-delete-task-id"
SCHEDULE_DELETE_IDS_KEY = "design-schedule-delete-task-ids"
SCHEDULE_DELETE_BUSY_KEY = "design-schedule-delete-busy"
SCHEDULE_SELECTION_SCOPE_KEY = "design-schedule-selection-scope"
SCHEDULE_TABLE_REVISION_KEY = "design-schedule-table-revision"

DESIGN_SCHEDULE_VIEWS = (
    "Active Designs",
    "Product Uploads",
    "Collections",
    "Updated Products",
    "Completed",
)

VIEW_TASK_FILTERS = {
    "Active Designs": ("open", sports_cave_dashboard.DESIGN_TASK_GROUP),
    "Product Uploads": ("open", sports_cave_dashboard.UPLOAD_TASK_GROUP),
    "Collections": ("open", sports_cave_dashboard.COLLECTIONS_TASK_GROUP),
    "Updated Products": ("open", sports_cave_dashboard.VARIANTS_TASK_GROUP),
    "Completed": ("complete", None),
}

DESIGN_TASK_TABLE_COLUMNS = (
    ("design_title", "Design title"),
    ("design_style", "Design style"),
    ("sport", "Sport"),
    ("principal_subject_one", "Principal subject one"),
    ("principal_subject_two", "Principal subject two"),
    ("priority", "Priority"),
    ("team_country", "Team/country"),
    ("season_era", "Season/era"),
    ("event_moment", "Event/moment"),
    ("venue_location", "Venue/location"),
    ("uniform_equipment_livery", "Uniform/equipment/livery"),
    ("essential_text", "Essential text"),
    ("special_instructions", "Special instructions"),
    ("league_or_competition", "League/competition"),
    ("team_or_athlete", "Team/athlete"),
    ("moment_or_theme", "Moment/theme"),
    ("design_description", "Design description"),
    ("due_date", "Due date"),
    ("notes", "Notes"),
    ("task", "Task"),
    ("category", "Category"),
    ("task_section", "Task section"),
    ("task_title", "Task title"),
)


def _inject_styles(*, mixed_selection=False):
    st.markdown(
        """
        <style>
        section[data-testid="stMain"]:has(.st-key-design-schedule) .block-container { padding-top: 1rem; }
        .st-key-design-schedule [data-testid="stVerticalBlock"] { gap: .4rem; }
        .st-key-design-schedule-header h1 { font-size: 1.5rem; line-height: 32px; padding: 0; margin: 0; letter-spacing: -.02em; }
        .st-key-design-schedule :is(button, input, [data-baseweb="select"]) { font-size: 13px; }
        .st-key-design-schedule :is([data-testid="stButton"], [data-testid="stDownloadButton"]) button {
            min-height: 32px; padding: 3px 10px; border-radius: 4px;
        }
        .st-key-design-schedule [data-testid="stWidgetLabel"] { min-height: 0; margin-bottom: 2px; }
        .st-key-design-schedule [data-testid="stWidgetLabel"] p { font-size: 12px; }
        .st-key-design-schedule [data-baseweb="input"],
        .st-key-design-schedule [data-baseweb="select"] > div { min-height: 32px; }
        .st-key-design-schedule [data-testid="stTextInput"] input { min-height: 30px; padding: 4px 9px; }
        .st-key-design-schedule [data-testid="stButtonGroup"] { margin: 0; }
        .st-key-design-schedule [data-testid="stButtonGroup"] button { min-height: 30px; border-radius: 4px; padding: 3px 12px; }
        .st-key-design-schedule [data-testid="stButtonGroup"] button:is([aria-pressed="true"], [data-testid="stBaseButton-segmented_controlActive"]) { background: #eee7d7 !important; border-color: #b79243 !important; color: #27231d !important; }
        .st-key-design-schedule-actions { border-top: 1px solid #ded8cb; padding-top: 5px; }
        .st-key-design-schedule-actions [data-testid="stCaptionContainer"] p { font-size: 12px; line-height: 30px; margin: 0; white-space: nowrap; }
        .st-key-design-schedule-actions [data-testid="stButton"] button { background: #fffdf8 !important; border: 1px solid #cfc8bb !important; }
        .st-key-design-schedule-actions [class*="st-key-design-schedule-delete"] button { color: #a63c32 !important; border-color: #d9b9b4 !important; background: #fff7f5 !important; }
        .st-key-design-schedule-actions [class*="st-key-design-schedule-delete"] button * { color: #a63c32 !important; }
        .st-key-design-schedule-actions button:disabled { opacity: .45 !important; }
        .st-key-design-schedule [data-testid="stDataFrame"] { border: 1px solid #d9d5ca; border-radius: 4px; }
        /* Keep the native header marker discoverable at rest and show a mixed
           selection dash. The overlay never intercepts native grid clicks. */
        [class*="st-key-design-schedule-table--active-designs"] [data-testid="stDataFrame"]::after {
            content: ""; position: absolute; left: 9px; top: 10px; width: 14px; height: 14px;
            border: 1px solid #b8b6af; border-radius: 3px; pointer-events: none;
            background-image: SELECTION_HEADER_FILL; background-size: 8px 2px;
            background-position: center; background-repeat: no-repeat;
        }
        @media (max-width: 1100px) {
            .st-key-design-schedule-header [data-testid="stHorizontalBlock"],
            .st-key-design-schedule-actions [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 6px !important; }
            .st-key-design-schedule .st-key-design-schedule-header [data-testid="stColumn"],
            .st-key-design-schedule .st-key-design-schedule-actions [data-testid="stColumn"] { flex: 1 1 130px !important; min-width: 130px !important; width: auto !important; }
            .st-key-design-schedule .st-key-design-schedule-header [data-testid="stColumn"]:first-child { flex-basis: 100% !important; min-height: 36px; }
        }
        @media (max-width: 600px) {
            .st-key-design-schedule-filters [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 6px !important; }
            .st-key-design-schedule .st-key-design-schedule-filters div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { flex: 1 1 140px !important; min-width: 140px !important; width: auto !important; }
            .st-key-design-schedule .st-key-design-schedule-filters div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child,
            .st-key-design-schedule .st-key-design-schedule-actions [data-testid="stColumn"]:first-child { flex-basis: 100% !important; }
            .st-key-design-schedule :is([data-testid="stButton"], [data-testid="stDownloadButton"]) button { min-height: 36px !important; height: 36px !important; }
            .st-key-design-schedule [data-testid="stButtonGroup"] > div { flex-wrap: wrap; }
        }
        .sc-selected-design { align-items: center; background: #f8f6f1; border: 1px solid #ded8cb; border-left: 2px solid #b79243; border-radius: 5px; display: flex; gap: .55rem; margin: .45rem 0 .65rem; min-height: 38px; overflow: hidden; padding: .45rem .65rem; white-space: nowrap; }
        .sc-selected-design span { color: #756f65; font-size: .7rem; font-weight: 700; text-transform: uppercase; }
        .sc-selected-design strong { color: #211f1b; font-size: .82rem; overflow: hidden; text-overflow: ellipsis; }
        .sc-schedule-allocation { border-left: 2px solid #b79243; color: #5f5a52; font-size: .8rem; margin: .35rem 0 .55rem; padding: .3rem .55rem; }
        .sc-schedule-allocation.invalid { border-color: #a33c32; color: #8b2f27; }
        section[data-testid="stMain"] .st-key-design-schedule-import-trigger div[data-testid="stButton"] button,
        section[data-testid="stMain"] .st-key-design-schedule-template div[data-testid="stDownloadButton"] button,
        section[data-testid="stMain"] .st-key-design-schedule-export-trigger div[data-testid="stButton"] button,
        section[data-testid="stMain"] .st-key-design-schedule-add-trigger div[data-testid="stButton"] button {
            background: #fffdf8 !important;
            border: 1px solid #cfc8bb !important;
            color: #27231d !important;
        }
        section[data-testid="stMain"] .st-key-design-schedule-import-trigger button *,
        section[data-testid="stMain"] .st-key-design-schedule-template button *,
        section[data-testid="stMain"] .st-key-design-schedule-export-trigger button *,
        section[data-testid="stMain"] .st-key-design-schedule-add-trigger button * {
            color: #27231d !important;
        }
        section[data-testid="stMain"] .st-key-design-schedule-import-trigger button:hover,
        section[data-testid="stMain"] .st-key-design-schedule-template button:hover,
        section[data-testid="stMain"] .st-key-design-schedule-export-trigger button:hover,
        section[data-testid="stMain"] .st-key-design-schedule-add-trigger button:hover {
            background: #f7f3ea !important;
            border-color: #b79243 !important;
        }
        </style>
        """.replace("SELECTION_HEADER_FILL", "linear-gradient(#7b622c, #7b622c)" if mixed_selection else "none"),
        unsafe_allow_html=True,
    )


def _format_timestamp(value, user=None):
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        import os_accounts

        parsed = parsed.astimezone(os_accounts.timezone_for_user(user or {}))
    except Exception:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%d %b %Y, %I:%M %p").lstrip("0")


def _selected_indices(event):
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    return list(rows or [])


def _display_rows(rows, *, design_view, user=None):
    if design_view:
        output = []
        for row in rows:
            display = {}
            for field, label in DESIGN_TASK_TABLE_COLUMNS:
                value = row.get(field) or ""
                if field == "design_style":
                    value = design_studio_styles.design_style_label(value)
                display[label] = value
            output.append(display)
        return output
    return [
        {
            "Task": row.get("task") or "",
            "Section": row.get("task_section") or row.get("category") or "",
            "Priority": row.get("priority") or "",
            "Due date": row.get("due_date") or "",
            "Notes": row.get("notes") or "",
            "Added": _format_timestamp(row.get("_created_at"), user),
        }
        for row in rows
    ]


def _reset_import(*, keep_open=False):
    st.session_state[SCHEDULE_IMPORT_OPEN_KEY] = bool(keep_open)
    st.session_state.pop(SCHEDULE_IMPORT_PREVIEW_KEY, None)
    st.session_state[SCHEDULE_IMPORT_NONCE_KEY] = int(
        st.session_state.get(SCHEDULE_IMPORT_NONCE_KEY, 0)
    ) + 1


def _render_import_preview(preview):
    counts = (
        ("Valid new", int(preview.get("new_count") or 0)),
        ("Will reactivate", int(preview.get("reactivate_count") or 0)),
        ("Active duplicates", int(preview.get("active_duplicate_count") or 0)),
        ("Completed duplicates", int(preview.get("completed_duplicate_count") or 0)),
        ("Invalid", int(preview.get("invalid_count") or 0)),
        ("Total rows", int(preview.get("total_row_count") or 0)),
    )
    columns = st.columns(len(counts), gap="small")
    for column, (label, value) in zip(columns, counts):
        column.metric(label, value)

    rows = []
    for item, status in (
        *((task, task.get("intended_action") or "Valid new") for task in preview.get("tasks", [])),
        *((item, item.get("intended_action") or "Existing active duplicate") for item in preview.get("duplicates", [])),
        *((item, "Invalid") for item in preview.get("errors", [])),
    ):
        values = dict(item.get("values") or {})
        rows.append(
            {
                "Row": item.get("row_number"),
                "Task title": values.get("task_title") or item.get("title") or "",
                "Section": values.get("task_section") or item.get("section") or "",
                "Design style": values.get("design_style") or "",
                "Principal subject one": values.get("principal_subject_one") or "",
                "Principal subject two": values.get("principal_subject_two") or "",
                "Intended action": status,
                "Validation result": "; ".join(item.get("errors") or []) or "Valid",
            }
        )
    if rows:
        rows.sort(key=lambda row: int(row.get("Row") or 0))
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            height=min(380, 48 + (len(rows) * 35)),
            row_height=32,
        )
    if preview.get("errors"):
        st.download_button(
            "Download error CSV",
            data=sports_cave_dashboard.build_task_import_error_csv(preview),
            file_name="sports-cave-task-import-errors.csv",
            mime="text/csv",
            key="design-schedule-import-errors",
        )


def _render_import_dialog():
    if not st.session_state.get(SCHEDULE_IMPORT_OPEN_KEY):
        return

    @st.dialog("Import Tasks CSV", width="large")
    def dialog():
        uploaded = st.file_uploader(
            "Completed task CSV",
            type=["csv"],
            accept_multiple_files=False,
            key=f"design-schedule-import-upload::{st.session_state.get(SCHEDULE_IMPORT_NONCE_KEY, 0)}",
        )
        preview = None
        if uploaded is not None:
            source_bytes = uploaded.getvalue()
            digest = hashlib.sha256(source_bytes).hexdigest()
            cached = st.session_state.get(SCHEDULE_IMPORT_PREVIEW_KEY) or {}
            if cached.get("digest") != digest or cached.get("filename") != uploaded.name:
                try:
                    preview = sports_cave_dashboard.preview_task_csv_import(
                        source_bytes,
                        uploaded.name,
                        existing_tasks=sports_cave_dashboard.list_tasks(
                            status="all",
                            limit=5000,
                        ),
                    )
                except sports_cave_dashboard.TaskCSVImportError as error:
                    st.warning(str(error))
                else:
                    st.session_state[SCHEDULE_IMPORT_PREVIEW_KEY] = {
                        "digest": digest,
                        "filename": uploaded.name,
                        "preview": preview,
                    }
            else:
                preview = cached.get("preview")
        if preview:
            _render_import_preview(preview)

        actions = st.columns(2)
        if actions[0].button("Cancel", key="design-schedule-import-cancel", use_container_width=True):
            _reset_import()
            st.rerun()
        affected = int((preview or {}).get("valid_count") or 0)
        if actions[1].button(
            f"Import {affected} design task{'s' if affected != 1 else ''}",
            key="design-schedule-import-confirm",
            type="primary",
            disabled=not preview or affected <= 0,
            use_container_width=True,
        ):
            try:
                result = sports_cave_dashboard.import_task_csv_preview(preview)
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error) or "Could not import the task CSV right now.")
                return
            st.session_state[SCHEDULE_TOAST_KEY] = (
                sports_cave_dashboard.format_task_import_result_message(result)
            )
            st.session_state[SCHEDULE_VIEW_KEY] = "Active Designs"
            _reset_import()
            st.rerun()

    dialog()


def _render_export_dialog():
    if not st.session_state.get(SCHEDULE_EXPORT_OPEN_KEY):
        return

    @st.dialog("Export Tasks CSV")
    def dialog():
        try:
            tasks = sports_cave_dashboard.list_tasks(status="open", limit=5000)
        except sports_cave_dashboard.DashboardStorageError as error:
            st.warning(str(error))
            tasks = []
        st.caption(f"{len(tasks)} active task{'s' if len(tasks) != 1 else ''} ready to export.")
        st.download_button(
            "Download CSV",
            data=sports_cave_dashboard.build_task_import_template_csv(tasks),
            file_name=sports_cave_dashboard.TASK_EXPORT_FILENAME,
            mime="text/csv",
            key="design-schedule-export-download",
            use_container_width=True,
        )
        if st.button("Close", key="design-schedule-export-close", use_container_width=True):
            st.session_state[SCHEDULE_EXPORT_OPEN_KEY] = False
            st.rerun()

    dialog()


def _render_add_dialog():
    if not st.session_state.get(SCHEDULE_ADD_OPEN_KEY):
        return

    @st.dialog("Add Task")
    def dialog():
        task_text = st.text_input("Task", placeholder="Add a task", key="design-schedule-add-text")
        category = st.selectbox(
            "Task section",
            sports_cave_dashboard.TASK_GROUPS,
            index=1,
            key="design-schedule-add-section",
        )
        design_style = ""
        if category == sports_cave_dashboard.DESIGN_TASK_GROUP:
            design_style = st.selectbox(
                "Design style",
                alphabetize_options(
                    ["", *design_studio_styles.style_slugs()],
                    label=design_studio_styles.design_style_label,
                ),
                format_func=design_studio_styles.design_style_label,
                key="design-schedule-add-style",
            )
        actions = st.columns(2)
        if actions[0].button("Cancel", key="design-schedule-add-cancel", use_container_width=True):
            st.session_state[SCHEDULE_ADD_OPEN_KEY] = False
            st.rerun()
        if actions[1].button(
            "Add task",
            key="design-schedule-add-confirm",
            type="primary",
            use_container_width=True,
        ):
            try:
                sports_cave_dashboard.add_task(
                    task_text,
                    category,
                    design_style=design_style,
                )
            except (ValueError, sports_cave_dashboard.DashboardStorageError) as error:
                st.warning(str(error))
                return
            view_by_section = {
                sports_cave_dashboard.DESIGN_TASK_GROUP: "Active Designs",
                sports_cave_dashboard.UPLOAD_TASK_GROUP: "Product Uploads",
                sports_cave_dashboard.COLLECTIONS_TASK_GROUP: "Collections",
                sports_cave_dashboard.VARIANTS_TASK_GROUP: "Updated Products",
            }
            st.session_state[SCHEDULE_VIEW_KEY] = view_by_section.get(category, "Active Designs")
            st.session_state[SCHEDULE_ADD_OPEN_KEY] = False
            st.session_state[SCHEDULE_TOAST_KEY] = "Task added."
            st.rerun()

    dialog()


def _style_mix_key(style_slug):
    return f"design-schedule-idea-style::{style_slug}"


def _initialise_idea_controls():
    sport_key = "design-schedule-idea-sport"
    total_key = "design-schedule-idea-total"
    normalize_sport_state(st.session_state, sport_key, "Other")
    st.session_state.setdefault(sport_key, sports_cave_dashboard.DESIGN_IDEA_SPORTS[0])
    st.session_state.setdefault(total_key, sports_cave_dashboard.DESIGN_IDEA_DEFAULT_TOTAL)
    mix = sports_cave_dashboard.suggest_design_idea_style_mix(
        st.session_state[sport_key],
        st.session_state[total_key],
    )
    for style_slug in sports_cave_dashboard.DESIGN_IDEA_STYLE_SLUGS:
        st.session_state.setdefault(_style_mix_key(style_slug), mix[style_slug])


def _suggest_best_mix():
    import design_studio_sales_intelligence as intelligence
    mix = sports_cave_dashboard.suggest_design_idea_style_mix(
        st.session_state["design-schedule-idea-sport"],
        st.session_state["design-schedule-idea-total"],
    )
    snapshot = intelligence.get_snapshot(st.session_state["design-schedule-idea-sport"])
    mix, reason = intelligence.suggest_evidence_mix(mix, snapshot)
    st.session_state["design-schedule-idea-intelligence"] = snapshot
    st.session_state["design-schedule-idea-mix-reason"] = reason
    for style_slug, count in mix.items():
        st.session_state[_style_mix_key(style_slug)] = count
    st.session_state.pop("design-schedule-idea-prompt", None)


def _render_idea_generator(copy_prompt_renderer=None):
    if not st.session_state.get(SCHEDULE_GENERATOR_OPEN_KEY):
        return
    _initialise_idea_controls()
    with st.container(border=True):
        top = st.columns([1.7, .8], gap="medium")
        sport = top[0].selectbox(
            "Sport or collection",
            alphabetize_options(sports_cave_dashboard.DESIGN_IDEA_SPORTS),
            key="design-schedule-idea-sport",
        )
        total = top[1].number_input(
            "Number of design ideas",
            min_value=1,
            max_value=30,
            step=1,
            key="design-schedule-idea-total",
        )
        st.markdown("**Design style mix**")
        mix = {}
        columns = st.columns(2, gap="medium")
        for index, (style_slug, style_label) in enumerate(
            sports_cave_dashboard.DESIGN_IDEA_STYLE_FIELDS
        ):
            mix[style_slug] = columns[index % 2].number_input(
                style_label,
                min_value=0,
                max_value=30,
                step=1,
                key=_style_mix_key(style_slug),
            )
        allocated = sports_cave_dashboard.design_idea_style_mix_total(mix)
        valid = allocated == int(total)
        st.markdown(
            f'<div class="sc-schedule-allocation{"" if valid else " invalid"}">'
            f"Allocated: {allocated} of {int(total)} designs</div>",
            unsafe_allow_html=True,
        )
        if not valid:
            st.caption("Adjust the style counts so the allocation matches the requested total.")
        if (st.session_state.get("design-schedule-idea-mix-reason")
                and (st.session_state.get("design-schedule-idea-intelligence") or {}).get("sport") == sport):
            st.caption(st.session_state["design-schedule-idea-mix-reason"])
        options = st.columns(2)
        exclude_existing = options[0].checkbox(
            "Exclude ideas already sold by Sports Cave",
            value=True,
            key="design-schedule-idea-exclude-existing",
        )
        calendar_relevance = options[1].checkbox(
            "Consider upcoming anniversaries and current sporting relevance",
            value=True,
            key="design-schedule-idea-calendar-relevance",
        )
        brief_scope = (sport, int(total), tuple(sorted(mix.items())), exclude_existing, calendar_relevance)
        if st.session_state.get("design-schedule-idea-prepared-scope") != brief_scope:
            st.session_state.pop("design-schedule-idea-prompt", None)
        actions = st.columns([1, 1.25, 2.5], gap="small")
        actions[0].button(
            "Suggest Best Mix",
            key="design-schedule-idea-suggest",
            on_click=_suggest_best_mix,
            use_container_width=True,
        )
        if actions[1].button(
            "Prepare Design Brief",
            key="design-schedule-idea-prepare",
            type="primary",
            disabled=not valid,
            use_container_width=True,
        ):
            try:
                import design_studio_sales_intelligence as intelligence
                snapshot = intelligence.get_snapshot(sport)
                st.session_state["design-schedule-idea-intelligence"] = snapshot
                st.session_state["design-schedule-idea-prompt"] = (
                    sports_cave_dashboard.build_new_design_ideas_prompt(
                        sport,
                        total,
                        mix,
                        exclude_existing=exclude_existing,
                        calendar_relevance=calendar_relevance,
                        intelligence_snapshot=snapshot,
                    )
                )
                st.session_state["design-schedule-idea-prepared-scope"] = brief_scope
            except ValueError as error:
                st.warning(str(error))
        import design_studio_intelligence_ui
        snapshot = st.session_state.get("design-schedule-idea-intelligence")
        if snapshot and snapshot.get("sport") == sport:
            design_studio_intelligence_ui.render_summary(snapshot, key="schedule-v3", sport=sport)
        prompt = str(st.session_state.get("design-schedule-idea-prompt") or "")
        if prompt:
            st.text_area(
                "Design brief prompt",
                value=prompt,
                height=300,
                disabled=True,
                key="design-schedule-idea-prompt-preview",
            )
            prompt_actions = st.columns([.9, 1.25, 3], gap="small")
            if copy_prompt_renderer:
                with prompt_actions[0]:
                    copy_prompt_renderer(prompt, "design-schedule-ideas", "Copy prompt")
            with prompt_actions[1]:
                st.download_button(
                    "Download prompt as TXT",
                    data=prompt.encode("utf-8"),
                    file_name="sports-cave-design-ideas-brief.txt",
                    mime="text/plain",
                    key="design-schedule-idea-download",
                    use_container_width=True,
                )


def _task_details(task):
    details = sports_cave_dashboard.task_import_details(task)
    return {
        key: details.get(key) or ""
        for key in sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS
    }


def _render_details_dialog(user=None):
    task_id = str(st.session_state.get(SCHEDULE_DETAILS_TASK_KEY) or "")
    if not task_id:
        return
    try:
        task = sports_cave_dashboard.get_task(task_id)
    except sports_cave_dashboard.DashboardStorageError as error:
        st.warning(str(error))
        return
    if not task:
        st.session_state.pop(SCHEDULE_DETAILS_TASK_KEY, None)
        return

    @st.dialog("View/Edit Details", width="large")
    def dialog():
        if (task.get("section") or task.get("category")) == sports_cave_dashboard.DESIGN_TASK_GROUP:
            current_style = sports_cave_dashboard.task_design_style(task)
            style_options = alphabetize_options(
                ["", *design_studio_styles.style_slugs()],
                label=design_studio_styles.design_style_label,
            )
            selected_style = st.selectbox(
                "Design style",
                style_options,
                index=selected_option_index(style_options, current_style),
                format_func=design_studio_styles.design_style_label,
                key=f"design-schedule-edit-style::{task_id}",
            )
            current = sports_cave_dashboard.design_task_details(task)
            values = {}
            columns = st.columns(2, gap="small")
            multiline = {
                "event_moment",
                "uniform_equipment_livery",
                "essential_text",
                "special_instructions",
            }
            for index, (field, label) in enumerate(design_studio_styles.DESIGN_DETAIL_FIELDS):
                target = columns[index % 2]
                if field in multiline:
                    values[field] = target.text_area(
                        label,
                        value=current.get(field) or "",
                        height=88,
                        key=f"design-schedule-edit::{task_id}::{field}",
                    )
                else:
                    values[field] = target.text_input(
                        label,
                        value=current.get(field) or "",
                        key=f"design-schedule-edit::{task_id}::{field}",
                    )
            if st.button(
                "Save design details",
                key=f"design-schedule-edit-save::{task_id}",
                type="primary",
                disabled=not selected_style,
                use_container_width=True,
            ):
                try:
                    sports_cave_dashboard.update_task_design_details(
                        task_id,
                        selected_style,
                        values,
                    )
                except (ValueError, sports_cave_dashboard.DashboardStorageError) as error:
                    st.warning(str(error))
                    return
                st.session_state.pop(SCHEDULE_DETAILS_TASK_KEY, None)
                st.session_state[SCHEDULE_TOAST_KEY] = "Design details saved."
                st.rerun()
        else:
            st.markdown(f"**{html.escape(str(task.get('title') or 'Task'))}**")
            rows = [
                {"Field": label, "Value": _task_details(task).get(key) or ""}
                for key, label in sports_cave_dashboard.TASK_IMPORT_DETAIL_FIELDS
                if _task_details(task).get(key)
            ]
            if rows:
                st.dataframe(rows, hide_index=True, width="stretch", height=300, row_height=TABLE_ROW_HEIGHT)
        if st.button("Close", key=f"design-schedule-details-close::{task_id}", use_container_width=True):
            st.session_state.pop(SCHEDULE_DETAILS_TASK_KEY, None)
            st.rerun()

    dialog()


def _clear_selected_design(task_id):
    if str(st.session_state.get(SELECTED_DESIGN_TASK_KEY) or "") != str(task_id or ""):
        return
    st.session_state.pop(SELECTED_DESIGN_TASK_KEY, None)
    st.session_state.pop(LOADED_DESIGN_TASK_KEY, None)


def _render_complete_dialog():
    task_id = str(st.session_state.get(SCHEDULE_COMPLETE_TASK_KEY) or "")
    if not task_id:
        return
    task = sports_cave_dashboard.get_task(task_id)
    if not task:
        st.session_state.pop(SCHEDULE_COMPLETE_TASK_KEY, None)
        return

    @st.dialog("Complete design task")
    def dialog():
        task_text = task.get("text") or task.get("title") or "Design task"
        st.write(task_text)
        scope = st.radio(
            "Mockups needed?",
            ("Website mockups", "All mockups"),
            horizontal=True,
            key=f"design-schedule-complete-scope::{task_id}",
        )
        actions = st.columns(2)
        if actions[0].button("Cancel", key=f"design-schedule-complete-cancel::{task_id}", use_container_width=True):
            st.session_state.pop(SCHEDULE_COMPLETE_TASK_KEY, None)
            st.rerun()
        if actions[1].button(
            "Move to upload",
            key=f"design-schedule-complete-confirm::{task_id}",
            type="primary",
            use_container_width=True,
        ):
            try:
                result = sports_cave_dashboard.complete_design_task_for_upload(
                    task_id,
                    task_text,
                    scope,
                )
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error))
                return
            if not result:
                st.warning("That task is no longer open.")
                return
            _clear_selected_design(task_id)
            st.session_state.pop(SCHEDULE_COMPLETE_TASK_KEY, None)
            st.session_state[SCHEDULE_TOAST_KEY] = "Design moved to Product Uploads."
            st.rerun()

    dialog()


def _render_delete_dialog(user=None):
    task_id = str(st.session_state.get(SCHEDULE_DELETE_TASK_KEY) or "")
    task_ids = list(st.session_state.get(SCHEDULE_DELETE_IDS_KEY) or ([task_id] if task_id else []))
    if not task_ids:
        return
    task = sports_cave_dashboard.get_task(task_ids[0]) or {}
    title = (
        sports_cave_dashboard.design_task_list_details(task).get("design_title")
        or task.get("title")
        or "Design task"
    )

    dialog_title = f'Delete "{title}"?' if len(task_ids) == 1 else f"Delete {len(task_ids)} designs?"

    @st.dialog(dialog_title)
    def dialog():
        st.write(
            f"This removes {len(task_ids)} selected design schedule task(s) only. "
            "It does not delete anything from Shopify. Artwork files, media and completed orders are preserved."
        )
        busy = bool(st.session_state.get(SCHEDULE_DELETE_BUSY_KEY))
        actions = st.columns(2)
        if actions[0].button("Cancel", key=f"design-schedule-delete-cancel::{task_id}", disabled=busy, use_container_width=True):
            st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
            st.session_state.pop(SCHEDULE_DELETE_IDS_KEY, None)
            st.rerun()
        confirm = actions[1].empty()
        if confirm.button(
            "Confirm Delete" if len(task_ids) > 1 else "Delete design",
            key=f"design-schedule-delete-confirm::{task_id}",
            type="primary",
            disabled=busy,
            use_container_width=True,
        ):
            # A queued click cannot replay a consumed confirmation.
            if busy or not (st.session_state.get(SCHEDULE_DELETE_TASK_KEY) or st.session_state.get(SCHEDULE_DELETE_IDS_KEY)):
                return
            st.session_state[SCHEDULE_DELETE_BUSY_KEY] = True
            confirm.button("Deleting...", key="design-schedule-delete-pending", disabled=True, use_container_width=True)
            try:
                if len(task_ids) == 1:
                    deleted = sports_cave_dashboard.delete_design_task(task_ids[0], user=user or {})
                else:
                    deleted = sports_cave_dashboard.delete_design_tasks(task_ids, user=user or {})
            except (PermissionError, sports_cave_dashboard.DashboardStorageError) as error:
                st.warning(str(error))
                return
            finally:
                st.session_state[SCHEDULE_DELETE_BUSY_KEY] = False
            if not deleted:
                st.warning("That design task is no longer active.")
                return
            for deleted_id in task_ids:
                _clear_selected_design(deleted_id)
            st.session_state[SCHEDULE_TABLE_REVISION_KEY] = int(st.session_state.get(SCHEDULE_TABLE_REVISION_KEY, 0)) + 1
            st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
            st.session_state.pop(SCHEDULE_DELETE_IDS_KEY, None)
            st.session_state[SCHEDULE_TOAST_KEY] = f'Deleted "{title}".' if len(task_ids) == 1 else f"Deleted {len(task_ids)} designs."
            st.rerun()

    dialog()


def _load_view_tasks(view):
    status, section = VIEW_TASK_FILTERS[view]
    tasks = sports_cave_dashboard.list_tasks(status=status, section=section, limit=5000)
    if view == "Active Designs":
        batch = tasks
        while len(batch) == 5000:
            batch = sports_cave_dashboard.list_tasks(status=status, section=section, limit=5000, offset=len(tasks))
            tasks.extend(batch)
    if section:
        rows = sports_cave_dashboard.task_table_rows(tasks, section)
    else:
        rows = []
        for group in sports_cave_dashboard.TASK_GROUPS:
            rows.extend(sports_cave_dashboard.task_table_rows(tasks, group))
        rows.sort(key=lambda row: str(row.get("_created_at") or ""), reverse=True)
    return tasks, rows


def _render_header(copy_prompt_renderer=None):
    with st.container(key="design-schedule-header"):
        _render_header_controls()
    _render_idea_generator(copy_prompt_renderer)


def _render_header_controls():
    columns = st.columns([1.5, 1, .85, .95, .85, .75], gap="small")
    columns[0].title("Design Studio")
    if columns[1].button(
        "Generate Ideas",
        key="design-schedule-generator-toggle",
        type="primary",
        use_container_width=True,
    ):
        st.session_state[SCHEDULE_GENERATOR_OPEN_KEY] = not bool(
            st.session_state.get(SCHEDULE_GENERATOR_OPEN_KEY)
        )
    if columns[2].button("Import CSV", key="design-schedule-import-trigger", use_container_width=True):
        _reset_import(keep_open=True)
    columns[3].download_button(
        "CSV Template",
        data=sports_cave_dashboard.build_task_import_template_csv(),
        file_name=sports_cave_dashboard.TASK_IMPORT_TEMPLATE_FILENAME,
        mime="text/csv",
        key="design-schedule-template",
        use_container_width=True,
    )
    if columns[4].button("Export CSV", key="design-schedule-export-trigger", use_container_width=True):
        st.session_state[SCHEDULE_EXPORT_OPEN_KEY] = True
    if columns[5].button("Add Task", key="design-schedule-add-trigger", use_container_width=True):
        st.session_state[SCHEDULE_ADD_OPEN_KEY] = True


def _selected_task_record(tasks):
    task_id = str(st.session_state.get(SELECTED_DESIGN_TASK_KEY) or "")
    if not task_id:
        return None
    task = next((item for item in tasks if str(item.get("id") or "") == task_id), None)
    if task is None:
        task = sports_cave_dashboard.get_task(task_id)
    if not task or str(task.get("status") or "").casefold() != "open":
        _clear_selected_design(task_id)
        return None
    if (task.get("section") or task.get("category")) != sports_cave_dashboard.DESIGN_TASK_GROUP:
        _clear_selected_design(task_id)
        return None
    return task


def render_design_schedule(user=None, *, copy_prompt_renderer=None):
    with st.container(key="design-schedule"):
        return _render_schedule_contents(user, copy_prompt_renderer=copy_prompt_renderer)


def _render_schedule_contents(user=None, *, copy_prompt_renderer=None):
    st.session_state.setdefault(SCHEDULE_VIEW_KEY, "Active Designs")
    toast = st.session_state.pop(SCHEDULE_TOAST_KEY, "")
    if toast:
        ui_feedback.show_temporary_toast(
            components,
            toast,
            event_key=f"design-schedule:{hashlib.sha1(str(toast).encode('utf-8')).hexdigest()[:12]}",
        )

    view = str(st.session_state.get(SCHEDULE_VIEW_KEY) or "Active Designs")
    if view not in DESIGN_SCHEDULE_VIEWS:
        view = "Active Designs"
        st.session_state[SCHEDULE_VIEW_KEY] = view
    try:
        tasks, authoritative_rows = _load_view_tasks(view)
    except sports_cave_dashboard.DashboardStorageError as error:
        tasks, authoritative_rows = [], []
        st.warning(str(error) or "The design schedule could not load right now.")
    if view == "Active Designs":
        st.session_state[SCHEDULE_ACTIVE_COUNT_KEY] = len(authoritative_rows)

    _render_header(copy_prompt_renderer)
    selected_view = st.segmented_control(
        "Schedule view",
        DESIGN_SCHEDULE_VIEWS,
        key=SCHEDULE_VIEW_KEY,
        label_visibility="collapsed",
    )
    if selected_view and selected_view != view:
        st.rerun()

    design_view = view == "Active Designs"
    group_key = view.casefold().replace(" ", "-")
    if design_view:
        with st.container(key="design-schedule-filters"):
            filters = st.columns([2.2, 1, 1, .8], gap="small")
        search = filters[0].text_input(
            "Search designs",
            placeholder="Search designs",
            key=f"design-schedule-search::{group_key}",
        )
        style_options = alphabetize_options(
            ["", *{row.get("design_style") for row in authoritative_rows if row.get("design_style")}],
            label=lambda value: "All styles" if not value else design_studio_styles.design_style_label(value),
        )
        style = filters[1].selectbox(
            "Design style",
            style_options,
            format_func=lambda value: "All styles" if not value else design_studio_styles.design_style_label(value),
            key=f"design-schedule-style::{group_key}",
        )
        sports = alphabetize_options(
            ["", *{normalize_sport_category(row.get("sport"), row.get("sport")) for row in authoritative_rows if row.get("sport")}],
            label=lambda value: value or "All sports",
        )
        normalize_sport_state(st.session_state, f"design-schedule-sport::{group_key}", preserve_custom=True)
        sport = filters[2].selectbox(
            "Sport",
            sports,
            format_func=lambda value: value or "All sports",
            key=f"design-schedule-sport::{group_key}",
        )
        priorities = ["", *[value for value in ("High", "Medium", "Low") if any(row.get("priority") == value for row in authoritative_rows)]]
        priority = filters[3].selectbox(
            "Priority",
            priorities,
            format_func=lambda value: value or "All priorities",
            key=f"design-schedule-priority::{group_key}",
        )
        rows = sports_cave_dashboard.filter_task_table_rows(
            authoritative_rows,
            search=search,
            design_style=style,
            sport=sport,
            priority=priority,
        )
    else:
        search = st.text_input(
            f"Search {view}",
            placeholder="Search tasks",
            key=f"design-schedule-search::{group_key}",
            label_visibility="collapsed",
        )
        rows = sports_cave_dashboard.filter_task_table_rows(authoritative_rows, search=search)

    # The native multi-row grid provides header select-all, mixed state and virtualisation.
    # Bind its identity to the full filtered ID set AND filter values, never row positions.
    scope = repr((view, search, (style, sport, priority) if design_view else (),
                  [row["_task_id"] for row in rows], st.session_state.get(SCHEDULE_TABLE_REVISION_KEY, 0)))
    if st.session_state.get(SCHEDULE_SELECTION_SCOPE_KEY) != scope:
        st.session_state[SCHEDULE_SELECTION_SCOPE_KEY] = scope
        st.session_state["design-schedule-selection-epoch"] = int(st.session_state.get("design-schedule-selection-epoch", 0)) + 1
        st.session_state[f"design-schedule-row::{group_key}"] = ""
    table_key = f"design-schedule-table::{group_key}::{st.session_state['design-schedule-selection-epoch']}"
    selected_ids = []
    if rows:
        event = st.dataframe(
            _display_rows(rows, design_view=design_view, user=user),
            hide_index=True,
            width="stretch",
            height=min(420, 36 + len(rows) * 32),
            row_height=32,
            column_config={label: st.column_config.TextColumn(label, width=240 if label in ("Design title", "Task") else 155)
                           for label in _display_rows(rows[:1], design_view=design_view, user=user)[0]},
            key=table_key,
            on_select="rerun",
            selection_mode="multi-row" if design_view else "single-row",
        )
        indices = _selected_indices(event)
        selected_ids = [rows[index]["_task_id"] for index in indices if 0 <= index < len(rows)]
    elif authoritative_rows:
        st.info("No tasks match the current search and filters.")
    else:
        st.caption("Nothing waiting.")

    _inject_styles(mixed_selection=design_view and 0 < len(selected_ids) < len(rows))
    row_id = selected_ids[0] if len(selected_ids) == 1 else ""
    st.session_state[f"design-schedule-row::{group_key}"] = row_id
    selected_row = next((row for row in rows if row.get("_task_id") == row_id), None)
    can_manage = sports_cave_dashboard.can_manage_dashboard_tasks(user or {})
    with st.container(key="design-schedule-actions"):
        actions = st.columns([1.25, 1, 1.15, .8, .95], gap="small")
    actions[0].caption(f"{len(rows)} {'designs' if design_view else 'tasks'} · {len(selected_ids)} selected")
    if actions[1].button(
        "Open in Studio",
        icon=":material/open_in_new:",
        key=f"design-schedule-open::{group_key}",
        disabled=not design_view or selected_row is None,
        use_container_width=True,
    ):
        st.session_state[SELECTED_DESIGN_TASK_KEY] = selected_row["_task_id"]
        st.session_state.pop(LOADED_DESIGN_TASK_KEY, None)
        st.rerun()
    if actions[2].button(
        "View/Edit Details",
        icon=":material/edit:",
        key=f"design-schedule-edit::{group_key}",
        disabled=selected_row is None,
        use_container_width=True,
    ):
        st.session_state[SCHEDULE_DETAILS_TASK_KEY] = selected_row["_task_id"]
        st.rerun()
    if actions[3].button(
        "Complete",
        icon=":material/check:",
        key=f"design-schedule-complete::{group_key}",
        disabled=selected_row is None or view == "Completed" or not can_manage,
        use_container_width=True,
    ):
        if design_view:
            st.session_state[SCHEDULE_COMPLETE_TASK_KEY] = selected_row["_task_id"]
            st.rerun()
        else:
            try:
                sports_cave_dashboard.complete_task(selected_row["_task_id"])
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error))
            else:
                st.session_state[SCHEDULE_TOAST_KEY] = "Task completed."
                st.rerun()
    if actions[4].button(
        "Delete selected" if len(selected_ids) > 1 else "Delete design",
        icon=":material/delete:",
        help="Delete design",
        key=f"design-schedule-delete::{group_key}",
        type="tertiary",
        disabled=not design_view or not selected_ids or not can_manage,
    ):
        if len(selected_ids) == 1:
            st.session_state[SCHEDULE_DELETE_TASK_KEY] = selected_row["_task_id"]
        else:
            st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
        st.session_state[SCHEDULE_DELETE_IDS_KEY] = selected_ids
        st.rerun()

    selected_task = _selected_task_record(tasks)
    if selected_task:
        details = sports_cave_dashboard.design_task_list_details(selected_task)
        subjects = " + ".join(
            value
            for value in (
                details.get("principal_subject_one"),
                details.get("principal_subject_two"),
            )
            if value
        )
        summary = " - ".join(
            value
            for value in (
                details.get("design_title") or selected_task.get("title"),
                details.get("design_style_label"),
                subjects,
                f"{details.get('priority')} priority" if details.get("priority") else "",
            )
            if value
        )
        st.markdown(
            '<div class="sc-selected-design"><span>Selected Design</span>'
            f"<strong>{html.escape(summary)}</strong></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sc-selected-design"><span>Selected Design</span>'
            "<strong>Select a design above to begin.</strong></div>",
            unsafe_allow_html=True,
        )

    _render_import_dialog()
    _render_export_dialog()
    _render_add_dialog()
    _render_details_dialog(user)
    _render_complete_dialog()
    _render_delete_dialog(user)
    return selected_task
