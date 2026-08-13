from datetime import datetime, timezone
import hashlib
import html

import streamlit as st

import design_studio_styles
import sports_cave_dashboard


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


def _inject_styles():
    st.markdown(
        """
        <style>
        .sc-design-schedule-title { align-items: baseline; display: flex; gap: .55rem; }
        .sc-design-schedule-title strong { color: #171512; font-size: 1.05rem; }
        .sc-design-schedule-count { color: #756f65; font-size: .76rem; }
        .sc-selected-design { align-items: center; background: #f8f6f1; border: 1px solid #ded8cb; border-left: 2px solid #b79243; border-radius: 5px; display: flex; gap: .55rem; margin: .45rem 0 .65rem; min-height: 38px; overflow: hidden; padding: .45rem .65rem; white-space: nowrap; }
        .sc-selected-design span { color: #756f65; font-size: .7rem; font-weight: 700; text-transform: uppercase; }
        .sc-selected-design strong { color: #211f1b; font-size: .82rem; overflow: hidden; text-overflow: ellipsis; }
        .sc-schedule-allocation { border-left: 2px solid #b79243; color: #5f5a52; font-size: .8rem; margin: .35rem 0 .55rem; padding: .3rem .55rem; }
        .sc-schedule-allocation.invalid { border-color: #a33c32; color: #8b2f27; }
        div[data-testid="stDataFrame"] { max-width: 100%; overflow: hidden; }
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
        """,
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
                ["", *design_studio_styles.style_slugs()],
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
    st.session_state.setdefault(sport_key, sports_cave_dashboard.DESIGN_IDEA_SPORTS[0])
    st.session_state.setdefault(total_key, sports_cave_dashboard.DESIGN_IDEA_DEFAULT_TOTAL)
    mix = sports_cave_dashboard.suggest_design_idea_style_mix(
        st.session_state[sport_key],
        st.session_state[total_key],
    )
    for style_slug in sports_cave_dashboard.DESIGN_IDEA_STYLE_SLUGS:
        st.session_state.setdefault(_style_mix_key(style_slug), mix[style_slug])


def _suggest_best_mix():
    mix = sports_cave_dashboard.suggest_design_idea_style_mix(
        st.session_state["design-schedule-idea-sport"],
        st.session_state["design-schedule-idea-total"],
    )
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
            sports_cave_dashboard.DESIGN_IDEA_SPORTS,
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
                st.session_state["design-schedule-idea-prompt"] = (
                    sports_cave_dashboard.build_new_design_ideas_prompt(
                        sport,
                        total,
                        mix,
                        exclude_existing=exclude_existing,
                        calendar_relevance=calendar_relevance,
                    )
                )
            except ValueError as error:
                st.warning(str(error))
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
            style_options = ["", *design_studio_styles.style_slugs()]
            selected_style = st.selectbox(
                "Design style",
                style_options,
                index=style_options.index(current_style) if current_style in style_options else 0,
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
                st.dataframe(rows, hide_index=True, width="stretch", height=300)
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
    if not task_id:
        return
    task = sports_cave_dashboard.get_task(task_id)
    if not task:
        st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
        return
    title = (
        sports_cave_dashboard.design_task_list_details(task).get("design_title")
        or task.get("title")
        or "Design task"
    )

    @st.dialog(f'Delete "{title}"?')
    def dialog():
        st.write(
            "This removes the design task from Sports Cave OS. "
            "It does not delete anything from Shopify."
        )
        actions = st.columns(2)
        if actions[0].button("Cancel", key=f"design-schedule-delete-cancel::{task_id}", use_container_width=True):
            st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
            st.rerun()
        if actions[1].button(
            "Delete design",
            key=f"design-schedule-delete-confirm::{task_id}",
            type="primary",
            use_container_width=True,
        ):
            try:
                deleted = sports_cave_dashboard.delete_design_task(task_id, user=user or {})
            except (PermissionError, sports_cave_dashboard.DashboardStorageError) as error:
                st.warning(str(error))
                return
            if not deleted:
                st.warning("That design task is no longer active.")
                return
            _clear_selected_design(task_id)
            st.session_state.pop(SCHEDULE_DELETE_TASK_KEY, None)
            st.session_state[SCHEDULE_TOAST_KEY] = f'Deleted "{title}".'
            st.rerun()

    dialog()


def _load_view_tasks(view):
    status, section = VIEW_TASK_FILTERS[view]
    tasks = sports_cave_dashboard.list_tasks(status=status, section=section, limit=5000)
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
    active_count = int(st.session_state.get(SCHEDULE_ACTIVE_COUNT_KEY) or 0)
    columns = st.columns([2.1, .78, .68, .72, .68, .62], gap="small")
    columns[0].markdown(
        '<div class="sc-design-schedule-title"><strong>Design Schedule</strong>'
        f'<span class="sc-design-schedule-count">{active_count} active design'
        f'{"s" if active_count != 1 else ""}</span></div>',
        unsafe_allow_html=True,
    )
    if columns[1].button(
        "Generate Ideas",
        key="design-schedule-generator-toggle",
        type="primary",
        use_container_width=True,
    ):
        st.session_state[SCHEDULE_GENERATOR_OPEN_KEY] = not bool(
            st.session_state.get(SCHEDULE_GENERATOR_OPEN_KEY)
        )
        st.rerun()
    if columns[2].button("Import CSV", key="design-schedule-import-trigger", use_container_width=True):
        _reset_import(keep_open=True)
        st.rerun()
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
        st.rerun()
    if columns[5].button("Add Task", key="design-schedule-add-trigger", use_container_width=True):
        st.session_state[SCHEDULE_ADD_OPEN_KEY] = True
        st.rerun()


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
    _inject_styles()
    st.session_state.setdefault(SCHEDULE_VIEW_KEY, "Active Designs")
    toast = st.session_state.pop(SCHEDULE_TOAST_KEY, "")
    if toast:
        st.toast(toast) if hasattr(st, "toast") else st.success(toast)

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
        filters = st.columns([2.2, 1, 1, .8], gap="small")
        search = filters[0].text_input(
            "Search designs",
            placeholder="Search designs",
            key=f"design-schedule-search::{group_key}",
        )
        style_options = ["", *sorted({row.get("design_style") for row in authoritative_rows if row.get("design_style")})]
        style = filters[1].selectbox(
            "Design style",
            style_options,
            format_func=lambda value: "All styles" if not value else design_studio_styles.design_style_label(value),
            key=f"design-schedule-style::{group_key}",
        )
        sports = ["", *sorted({row.get("sport") for row in authoritative_rows if row.get("sport")})]
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

    if rows:
        event = st.dataframe(
            _display_rows(rows, design_view=design_view, user=user),
            hide_index=True,
            width="stretch",
            height=420,
            row_height=34,
            key=f"design-schedule-table::{group_key}",
            on_select="rerun",
            selection_mode="single-row",
        )
        indices = _selected_indices(event)
        if indices and 0 <= indices[0] < len(rows):
            st.session_state[f"design-schedule-row::{group_key}"] = rows[indices[0]]["_task_id"]
    elif authoritative_rows:
        st.info("No tasks match the current search and filters.")
    else:
        st.caption("Nothing waiting.")

    row_id = str(st.session_state.get(f"design-schedule-row::{group_key}") or "")
    selected_row = next((row for row in rows if row.get("_task_id") == row_id), None)
    selected_raw = next((task for task in tasks if str(task.get("id") or "") == row_id), None)
    can_manage = sports_cave_dashboard.can_manage_dashboard_tasks(user or {})
    actions = st.columns([1.25, 1, 1.15, .8, .8], gap="small")
    actions[0].caption(f"{len(rows)} {'designs' if design_view else 'tasks'} - select one row for actions")
    if actions[1].button(
        "Open in Studio",
        icon=":material/open_in_new:",
        key=f"design-schedule-open::{group_key}",
        disabled=not design_view or selected_row is None,
        use_container_width=True,
    ):
        st.session_state[SELECTED_DESIGN_TASK_KEY] = selected_row["_task_id"]
        st.session_state.pop(LOADED_DESIGN_TASK_KEY, None)
        st.session_state["design-studio-scroll-to-workflow"] = True
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
        "Delete design",
        icon=":material/delete:",
        help="Delete design",
        key=f"design-schedule-delete::{group_key}",
        type="tertiary",
        disabled=not design_view or selected_raw is None or not can_manage,
    ):
        st.session_state[SCHEDULE_DELETE_TASK_KEY] = selected_row["_task_id"]
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
