import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import daily_activity_digest
import daily_activity_reporting
import email_service
import os_accounts
import reporting_store
import sports_cave_dashboard
from ui_option_ordering import alphabetize_options


ARCHIVE_PAGE_SIZE = 15
ACTIVITY_PAGE_SIZE = 25
HISTORY_SHEET_PAGE_SIZE = 40
PERIOD_KEY = "reporting-period"
CUSTOM_START_KEY = "reporting-custom-start"
CUSTOM_END_KEY = "reporting-custom-end"
PERIOD_OPTIONS = ("Today", "Last 7 days", "Last 30 days", "Custom")


def _format_timestamp(value, timezone_name=daily_activity_reporting.REPORT_TIMEZONE):
    if not value:
        return "Not yet"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        local_value = value.astimezone(ZoneInfo(timezone_name))
    except Exception:
        local_value = value.astimezone(timezone.utc)
    return local_value.strftime("%d %b %Y, %I:%M %p %Z")


def _delivery_status_label(status, *, local_now, send_hour):
    status = str(status or "").strip().casefold()
    if status:
        return status.title()
    if local_now.hour < send_hour:
        return "Scheduled"
    return "Awaiting hourly run"


def _load_today_snapshot(now_utc, mail_config, digest_config):
    period = daily_activity_reporting.build_report_period(
        now_utc,
        timezone_name=digest_config.timezone_name,
    )
    return daily_activity_reporting.collect_report_snapshot(
        period=period,
        recipient=mail_config.recipient,
        is_test=False,
    )


def _render_today(user, now_utc, digest_config, mail_config, storage_ready):
    local_now = now_utc.astimezone(ZoneInfo(digest_config.timezone_name))
    st.subheader("Today")
    try:
        snapshot = _load_today_snapshot(now_utc, mail_config, digest_config)
    except Exception:
        st.warning("Today's reporting summary could not load right now.")
        return None

    delivery = {}
    if storage_ready:
        try:
            delivery = reporting_store.today_delivery_status(
                user,
                snapshot["report_date"],
            )
        except Exception:
            delivery = {}
    metrics = st.columns(4)
    metrics[0].metric("Sydney report date", local_now.strftime("%d %b %Y"))
    metrics[1].metric(
        "Expected send",
        f"{digest_config.send_hour:02d}:00 {local_now.tzname()}",
    )
    metrics[2].metric(
        "Report status",
        _delivery_status_label(
            delivery.get("status"),
            local_now=local_now,
            send_hour=digest_config.send_hour,
        ),
    )
    metrics[3].metric("Meaningful actions", snapshot["summary"]["total_actions"])

    secondary = st.columns(3)
    secondary[0].metric(
        "Staff with activity",
        f"{snapshot['summary']['staff_with_activity']} / {snapshot['summary']['active_staff_count']}",
    )
    secondary[1].metric(
        "Daily Execution",
        (
            f"{snapshot['summary']['daily_execution_completed']} done / "
            f"{snapshot['summary']['daily_execution_outstanding']} open"
        ),
    )
    secondary[2].metric("Attention items", snapshot["summary"]["attention_count"])
    if snapshot["attention"]:
        st.warning("  \n".join(snapshot["attention"]))
    social = snapshot.get("social_media") or {}
    if social.get("staff_count"):
        st.markdown("#### Social Media")
        social_metrics = st.columns(4)
        social_metrics[0].metric(
            "Team completion",
            f"{int(social.get('completed_days') or 0)} / {int(social.get('staff_count') or 0)}",
        )
        social_metrics[1].metric("Posts live", int(social.get("posts_live") or 0))
        social_metrics[2].metric(
            "Average score",
            f"{float(social.get('average_score') or 0):.1f}/10",
        )
        social_metrics[3].metric(
            "Open MIPs",
            int(social.get("outstanding_mips") or 0),
        )
        by_platform = social.get("posts_live_by_platform") or {}
        if by_platform:
            st.caption(
                "Posts live by platform: "
                + " | ".join(
                    f"{platform} {count}"
                    for platform, count in sorted(by_platform.items())
                )
            )
        if social.get("blockers"):
            st.caption(f"{int(social['blockers'])} Social Media blocker(s) reported.")
    return snapshot


def _render_staff_summary(snapshot):
    if not snapshot:
        return
    st.subheader("Staff Summary")
    rows = []
    for member in snapshot["staff"]:
        daily = member.get("daily_execution") or {}
        social = member.get("social_media") or {}
        rows.append(
            {
                "Staff": member.get("display_name") or "Staff member",
                "Role": str(member.get("role") or "").title(),
                "Meaningful": int(member.get("total_actions") or 0),
                "Completed": int(member.get("completed_actions") or 0),
                "Failed": int(member.get("failed_actions") or 0),
                "Daily execution": (
                    f"{daily.get('completed_count', 0)}/{daily.get('task_count', 0)}"
                    if daily.get("exists") else "No sheet"
                ),
                "Social MIPs": int(social.get("mips_completed") or 0),
                "Last activity": _format_timestamp(
                    member.get("last_activity_at"), member.get("timezone")
                ) if member.get("last_activity_at") else "None",
            }
        )
    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            height=min(300, max(120, 29 * (len(rows) + 1))),
            row_height=28,
            key="reporting-staff-summary-table",
        )
    else:
        st.caption("No authorised staff activity was recorded for this report date.")


def _period_bounds(user):
    timezone_name = os_accounts.timezone_for_user(user) or daily_activity_reporting.REPORT_TIMEZONE
    local_today = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    st.session_state.setdefault(PERIOD_KEY, "Today")
    period = st.radio(
        "Reporting period",
        PERIOD_OPTIONS,
        horizontal=True,
        key=PERIOD_KEY,
    )
    if period == "Last 7 days":
        return local_today - timedelta(days=6), local_today, "Last 7 days"
    if period == "Last 30 days":
        return local_today - timedelta(days=29), local_today, "Last 30 days"
    if period == "Custom":
        st.session_state.setdefault(CUSTOM_START_KEY, local_today - timedelta(days=6))
        st.session_state.setdefault(CUSTOM_END_KEY, local_today)
        if hasattr(st, "popover"):
            with st.popover("Choose date range"):
                start_value = st.date_input("Start date", key=CUSTOM_START_KEY)
                end_value = st.date_input("End date", key=CUSTOM_END_KEY)
        else:
            cols = st.columns(2)
            start_value = cols[0].date_input("Start date", key=CUSTOM_START_KEY)
            end_value = cols[1].date_input("End date", key=CUSTOM_END_KEY)
        if end_value < start_value:
            st.warning("End date must be on or after the start date.")
            end_value = start_value
            st.session_state[CUSTOM_END_KEY] = start_value
        st.caption(f"Custom range: {start_value.strftime('%d %b %Y')} - {end_value.strftime('%d %b %Y')}")
        return start_value, end_value, "Custom"
    return local_today, local_today, "Today"


def _timer_timestamp(timer, key, user):
    return _format_timestamp((timer or {}).get(key), os_accounts.timezone_for_user(user) or daily_activity_reporting.REPORT_TIMEZONE)


def _render_daily_execution_history(user, start_date, end_date):
    st.subheader("Daily Execution History")
    signature = f"{start_date}:{end_date}"
    if st.session_state.get("reporting-history-range") != signature:
        st.session_state["reporting-history-range"] = signature
        st.session_state["reporting-history-page"] = 1
    page = max(int(st.session_state.get("reporting-history-page") or 1), 1)
    try:
        result = sports_cave_dashboard.list_daily_execution_history_page(
            user,
            start_date,
            end_date,
            page=page,
            page_size=HISTORY_SHEET_PAGE_SIZE,
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Daily Execution history could not load right now.")
        return
    rows = result.get("rows") or []
    if not rows:
        st.caption("No Daily Planner tasks found on this page.")
    table_rows = []
    for row in rows:
        timer = row.get("timer") or {}
        actual_elapsed = (
            timer.get("actual_elapsed_seconds")
            if timer.get("actual_elapsed_seconds") is not None
            else row.get("actual_elapsed_seconds")
        )
        completion_method = str(
            row.get("completion_method") or timer.get("completion_method") or ""
        ).strip().casefold()
        table_rows.append(
            {
                "Work date": row.get("work_date") or "",
                "Task": row.get("task") or "",
                "Owner": row.get("owner") or "",
                "Category/area": row.get("category") or "",
                "Allocated duration": row.get("allocated") or (
                    sports_cave_dashboard.format_duration_seconds(row.get("allocated_seconds"))
                    if row.get("allocated_seconds")
                    else ""
                ),
                "Actual elapsed": (
                    sports_cave_dashboard.format_duration_seconds(actual_elapsed)
                    if actual_elapsed is not None
                    else ""
                ),
                "Time saved": sports_cave_dashboard.format_duration_seconds(row.get("time_saved_seconds")) if row.get("time_saved_seconds") else "",
                "Start time": _timer_timestamp(timer, "started_at", user),
                "End time": _timer_timestamp(timer, "outcome_at", user) or _format_timestamp(row.get("completed_at") or row.get("finished_at"), os_accounts.timezone_for_user(user)),
                "Status": row.get("status") or "Planned",
                "Outcome": _outcome_display(row.get("outcome") or timer.get("outcome")),
                "Completion method": "Finished early" if completion_method == "finished_early" else completion_method.replace("_", " ").title(),
                "Skip reason": row.get("skip_reason") or timer.get("skip_reason") or "",
                "Notes": row.get("notes") or "",
                "_row_id": row.get("row_id") or "",
            }
        )
    if table_rows:
        st.caption(
            f"{len(table_rows)} task record(s) from {result.get('sheet_count', 0)} sheet(s) on page {page}"
        )
        st.dataframe(
            table_rows,
            hide_index=True,
            use_container_width=True,
            height=min(520, max(240, 28 * (len(table_rows) + 1))),
            row_height=28,
            column_order=(
                "Work date",
                "Task",
                "Owner",
                "Category/area",
                "Allocated duration",
                "Actual elapsed",
                "Time saved",
                "Start time",
                "End time",
                "Status",
                "Outcome",
                "Completion method",
                "Skip reason",
                "Notes",
            ),
            key=f"reporting-daily-execution-history-{page}",
        )
    controls = st.columns([1, 1, 5])
    if controls[0].button(
        "Previous",
        disabled=not result.get("has_previous"),
        key="reporting-history-previous",
    ):
        st.session_state["reporting-history-page"] = max(page - 1, 1)
        st.rerun()
    if controls[1].button(
        "Next",
        disabled=not result.get("has_next"),
        key="reporting-history-next",
    ):
        st.session_state["reporting-history-page"] = page + 1
        st.rerun()
    controls[2].caption(
        f"Page {page} | Up to {HISTORY_SHEET_PAGE_SIZE} sheets per page"
    )


def _outcome_display(value):
    clean = str(value or "").strip().casefold()
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_COMPLETED:
        return "Completed"
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_DID_NOT_FINISH:
        return "Did not finish"
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_SKIPPED:
        return "Skipped"
    return ""


def _render_twelve_week_progress(user):
    st.subheader("Twelve Week Progress")
    try:
        progress = sports_cave_dashboard.load_twelve_week_progress(user)
    except sports_cave_dashboard.DashboardStorageError as error:
        st.info(str(error))
        return
    cycle = progress.get("cycle") or {}
    weeks = progress.get("weeks") or []
    if not cycle or not weeks:
        st.caption("No 12-week cycle has been set up for this account.")
        return
    st.caption(
        f"{cycle.get('name') or '12 Week Year'} | "
        f"{cycle.get('start_date')} - "
        f"{(date.fromisoformat(str(cycle.get('start_date'))) + timedelta(days=83)).isoformat()}"
    )
    table_rows = [
        {
            "Week": f"Week {week['week_number']}",
            "Date range": f"{date.fromisoformat(week['week_start']).strftime('%d/%m/%Y')}-{date.fromisoformat(week['week_end']).strftime('%d/%m/%Y')}",
            "Theme": week.get("theme") or "Not planned",
            "Objectives": f"{week.get('objective_count', 0)}/3",
            "Tactics": week.get("tactic_count", 0),
            "Tactic score": f"{round(week.get('tactic_score', 0))}%",
            "Daily score": f"{round(week.get('daily_score', 0))}%",
            "Focused time": sports_cave_dashboard.format_duration_seconds(week.get("focused_seconds")),
            "Completed": week.get("completed", 0),
            "Did not finish": week.get("did_not_finish", 0),
            "Skipped": week.get("skipped", 0),
            "Review": week.get("review") or "Not completed",
            "Details": "View week",
        }
        for week in weeks
    ]
    st.dataframe(
        table_rows,
        hide_index=True,
        use_container_width=True,
        height=390,
        row_height=28,
        key="reporting-twelve-week-progress",
    )
    selector_cols = st.columns([1.5, 1, 1, 1, 3])
    selected_label = selector_cols[0].selectbox(
        "Week details",
        tuple(f"Week {week['week_number']}" for week in weeks),
        label_visibility="collapsed",
        key="reporting-twelve-week-selected",
    )
    selected_week = weeks[int(selected_label.split()[-1]) - 1]
    if selector_cols[1].button("View week", key="reporting-view-week"):
        st.session_state["reporting-show-week-detail"] = selected_week["week_number"]
    if selector_cols[2].button("Weekly review", key="reporting-open-weekly-review"):
        st.session_state["reporting-weekly-review-week-date"] = date.fromisoformat(selected_week["week_start"])
        st.session_state["reporting-weekly-plan-id"] = selected_week.get("plan_id") or ""
        st.session_state["current_page"] = os_accounts.WEEKLY_REVIEW_ROUTE
        st.rerun()
    selected_month = next(
        (
            row
            for row in progress.get("months") or []
            if f"Week {selected_week['week_number']}" in str(row.get("weeks_included") or "")
        ),
        {},
    )
    if selector_cols[3].button(
        "Monthly review",
        disabled=not bool(selected_month.get("review_id")),
        key="reporting-open-monthly-review",
    ):
        st.session_state["reporting-monthly-review-id"] = selected_month["review_id"]
    if st.session_state.get("reporting-show-week-detail") == selected_week["week_number"]:
        st.markdown(
            f"**{selected_week.get('theme') or 'No weekly theme'}**  "
            f"{selected_week.get('quote_text') or 'No quote saved'}"
            + (f" - {selected_week.get('quote_author')}" if selected_week.get("quote_author") else "")
        )
        day_rows = [
            {
                "Day": row["day"],
                "Date": row["date"],
                "Major tasks": row["major_tasks"],
                "Completed": row["completed"],
                "Did not finish": row["did_not_finish"],
                "Skipped": row["skipped"],
                "Completion": f"{round(row['completion_percentage'])}%",
                "Focused time": sports_cave_dashboard.format_duration_seconds(row["focused_seconds"]),
                "Review": row["review"],
            }
            for row in selected_week.get("days") or []
        ]
        st.dataframe(
            day_rows,
            hide_index=True,
            use_container_width=True,
            height=245,
            row_height=28,
            key=f"reporting-week-days-{selected_week['week_number']}",
        )
        objective_rows = []
        for objective in selected_week.get("objectives") or []:
            tactics = objective.get("tactics") or []
            objective_rows.append(
                {
                    "Objective": objective.get("title") or "",
                    "Target": objective.get("measurable_target") or "",
                    "Result": str(objective.get("result") or "Not reviewed").replace("_", " ").title(),
                    "Tactics": len(tactics),
                    "Completed tactics": sum(str(tactic.get("status")) == "completed" for tactic in tactics),
                }
            )
        if objective_rows:
            st.dataframe(
                objective_rows,
                hide_index=True,
                use_container_width=True,
                height=min(180, 29 * (len(objective_rows) + 1)),
                row_height=28,
                key=f"reporting-week-objectives-{selected_week['week_number']}",
            )
        day_options = {
            row["date"]: row for row in selected_week.get("days") or [] if row.get("sheet_ids")
        }
        if day_options:
            detail_date = st.selectbox(
                "Daily Plan and Review",
                tuple(day_options),
                key=f"reporting-week-day-detail-{selected_week['week_number']}",
            )
            if st.button("Open day details", key=f"reporting-open-day-{selected_week['week_number']}"):
                sheet_id = day_options[detail_date]["sheet_ids"][0]
                try:
                    sheet = sports_cave_dashboard.get_daily_execution_archive_detail(user, sheet_id)
                except sports_cave_dashboard.DashboardStorageError:
                    sheet = {}
                if sheet:
                    st.session_state["reporting-day-detail"] = sheet
            detail = st.session_state.get("reporting-day-detail") or {}
            if detail and str(detail.get("sheet_date")) == detail_date:
                detail_rows = sports_cave_dashboard.daily_execution_task_rows(detail, [])
                st.dataframe(
                    [{"Task": row["task"], "Area": row["category"], "Allocated": row["allocated"], "Status": row["status"], "Notes": row["notes"]} for row in detail_rows],
                    hide_index=True,
                    use_container_width=True,
                    height=min(260, max(100, 29 * (len(detail_rows) + 1))),
                    row_height=28,
                    key=f"reporting-day-drawer-{detail_date}",
                )
                review = detail.get("review_data") or {}
                if review:
                    st.caption(
                        " | ".join(
                            f"{label}: {review.get(key)}"
                            for key, label in (("worked_well", "Win"), ("could_not_finish", "Blocker"), ("lesson", "Lesson"))
                            if review.get(key)
                        )
                    )
    st.markdown("#### Monthly Review")
    month_rows = [
        {
            "Month": row["month"],
            "Weeks included": row["weeks_included"],
            "Daily completion": f"{round(row['daily_completion'])}%",
            "Tactic execution": f"{round(row['tactic_execution'])}%",
            "Focused time": sports_cave_dashboard.format_duration_seconds(row["focused_seconds"]),
            "Objectives achieved": row["objectives_achieved"],
            "Reviews complete": row["reviews_complete"],
            "Monthly review": row["review"],
        }
        for row in progress.get("months") or []
    ]
    if month_rows:
        st.dataframe(
            month_rows,
            hide_index=True,
            use_container_width=True,
            height=min(240, max(100, 29 * (len(month_rows) + 1))),
            row_height=28,
            key="reporting-monthly-review-table",
        )
        saved_months = {
            row["review_id"]: row
            for row in progress.get("months") or []
            if row.get("review_id")
        }
        selected_review_id = st.session_state.get("reporting-monthly-review-id")
        if selected_review_id in saved_months:
            monthly = saved_months[selected_review_id]
            st.markdown(f"**{monthly['month']} monthly review**")
            st.caption(f"Weeks included: {monthly['weeks_included']}")
            summary_rows = [
                {"Field": str(key).replace("_", " ").title(), "Saved value": value}
                for key, value in (monthly.get("summary") or {}).items()
                if value not in (None, "", [], {})
            ]
            if summary_rows:
                st.dataframe(
                    summary_rows,
                    hide_index=True,
                    use_container_width=True,
                    height=min(260, max(100, 29 * (len(summary_rows) + 1))),
                    row_height=28,
                    key=f"reporting-monthly-review-detail-{selected_review_id}",
                )
            else:
                st.caption("This saved monthly review has no written summary fields.")


def _render_staff_week_activity(user, anchor_date):
    if not os_accounts.can_view_activity_log(user):
        return
    st.subheader("Staff Weekly Activity")
    try:
        snapshot = sports_cave_dashboard.build_reporting_staff_week_snapshot(
            user, anchor_date
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Staff activity could not load right now.")
        return
    rows = snapshot.get("staff_rows") or []
    if not rows:
        st.caption("No authorised staff activity was found for this week.")
        return
    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        height=min(280, max(120, 29 * (len(rows) + 1))),
        row_height=28,
        column_order=("Account", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Weekly total", "Last activity", "Details"),
        key="reporting-staff-week-activity",
    )
    details = snapshot.get("details") or []
    account_options = {row["Account"]: row["staff_id"] for row in rows}
    filter_cols = st.columns([1.4, 1, 1.4, 1.4])
    account = filter_cols[0].selectbox("Account", alphabetize_options(account_options), key="reporting-staff-detail-account")
    day = filter_cols[1].selectbox("Day", ("All", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), key="reporting-staff-detail-day")
    areas = alphabetize_options(("All", *{str(row.get("Area") or "") for row in details if row.get("Area")}))
    area = filter_cols[2].selectbox("Area", areas, key="reporting-staff-detail-area")
    sources = alphabetize_options(("All", *{str(row.get("Source") or "") for row in details if row.get("Source")}))
    source = filter_cols[3].selectbox("Activity type", sources, key="reporting-staff-detail-source")
    selected = [
        {key: value for key, value in row.items() if key not in {"staff_id", "day"}}
        for row in details
        if row.get("staff_id") == account_options[account]
        and (day == "All" or row.get("day") == day)
        and (area == "All" or row.get("Area") == area)
        and (source == "All" or row.get("Source") == source)
    ]
    if selected:
        st.dataframe(
            selected,
            hide_index=True,
            use_container_width=True,
            height=min(300, max(120, 29 * (len(selected) + 1))),
            row_height=28,
            key="reporting-staff-day-detail",
        )
    else:
        st.caption("No matching work records for this account and day.")


def _render_operational_activity(user, start_date, end_date):
    if not os_accounts.can_view_activity_log(user):
        return
    st.subheader("Human Work Records")
    filter_cols = st.columns([1.4, 1.1, 1.2, 1])
    staff_filter = filter_cols[0].text_input("Staff member", key="reporting-human-work-staff")
    area_filter = filter_cols[1].text_input("Area", key="reporting-human-work-area")
    action_type_filter = filter_cols[2].text_input("Action type", key="reporting-human-work-action")
    outcome_label = filter_cols[3].selectbox(
        "Outcome",
        ("All", "Completed", "Skipped", "Did not finish", "Failed"),
        key="reporting-human-work-outcome",
    )
    outcome_filter = {
        "Completed": "completed",
        "Skipped": "skipped",
        "Did not finish": "did_not_finish",
        "Failed": "failed",
    }.get(outcome_label, "")
    signature = f"{start_date}:{end_date}:{staff_filter}:{area_filter}:{action_type_filter}:{outcome_filter}"
    if st.session_state.get("reporting-human-work-range") != signature:
        st.session_state["reporting-human-work-range"] = signature
        st.session_state["reporting-activity-page"] = 1
    page = max(int(st.session_state.get("reporting-activity-page") or 1), 1)
    try:
        result = sports_cave_dashboard.list_human_work_entries_page(
            start_date,
            end_date,
            page=page,
            page_size=ACTIVITY_PAGE_SIZE,
            user=user,
            staff_filter=staff_filter,
            area_filter=area_filter,
            action_type_filter=action_type_filter,
            outcome_filter=outcome_filter,
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Human work records could not load right now.")
        return
    tzinfo = ZoneInfo(daily_activity_reporting.REPORT_TIMEZONE)
    records = [
        sports_cave_dashboard.human_work_table_record(entry, tzinfo)
        for entry in result.get("rows") or []
    ]
    if records:
        st.dataframe(
            records,
            hide_index=True,
            use_container_width=True,
            height=min(430, max(180, 29 * (len(records) + 1))),
            row_height=28,
            key=f"reporting-human-work-records-{page}",
        )
    else:
        st.caption("No human work records match these filters.")
    controls = st.columns([1, 1, 5])
    if controls[0].button("Previous", disabled=not result.get("has_previous"), key="reporting-activity-previous"):
        st.session_state["reporting-activity-page"] = max(page - 1, 1)
        st.rerun()
    if controls[1].button("Next", disabled=not result.get("has_next"), key="reporting-activity-next"):
        st.session_state["reporting-activity-page"] = page + 1
        st.rerun()
    controls[2].caption(f"Page {page} | Up to {ACTIVITY_PAGE_SIZE} records per page")


def _render_reporting_tables(user, now_utc):
    start_date, end_date, _label = _period_bounds(user)
    _render_twelve_week_progress(user)
    _render_daily_execution_history(user, start_date, end_date)
    _render_staff_week_activity(user, end_date)
    _render_operational_activity(user, start_date, end_date)


def _archive_label(row):
    prefix = "TEST | " if row.get("is_test") else ""
    return (
        f"{prefix}{row.get('report_date')} | {row.get('status', '').title()} | "
        f"{row.get('subject') or 'Daily staff report'}"
    )


def _render_sent_reports(user, storage_ready):
    st.subheader("Sent Reports")
    if not storage_ready:
        st.info(
            f"Apply `migrations/{reporting_store.REPORTING_MIGRATION}` to enable the report archive."
        )
        return
    filter_cols = st.columns([1, 1, 1, 1])
    today = datetime.now(timezone.utc).astimezone(daily_activity_reporting.SYDNEY_TZ).date()
    start_date = filter_cols[0].date_input(
        "From",
        value=today - timedelta(days=30),
        key="reporting-archive-from",
    )
    status_filter = filter_cols[1].selectbox(
        "Status",
        ("All", "Sent", "Failed", "Pending"),
        key="reporting-archive-status",
    )
    staff_filter = filter_cols[2].text_input(
        "Staff",
        key="reporting-archive-staff",
    )
    page = filter_cols[3].number_input(
        "Page",
        min_value=1,
        value=1,
        step=1,
        key="reporting-archive-page",
    )
    try:
        rows = reporting_store.list_archives(
            user,
            page=page,
            page_size=ARCHIVE_PAGE_SIZE,
            start_date=start_date,
            end_date=today,
            staff_filter=staff_filter,
            status_filter=status_filter,
        )
    except PermissionError:
        st.error("Reporting access is not approved.")
        return
    except Exception:
        st.warning("The report archive could not load right now.")
        return
    if not rows:
        st.caption("No archived reports match these filters.")
        return

    table_rows = []
    for row in rows:
        summary = row.get("report_summary") or {}
        table_rows.append(
            {
                "Date": str(row.get("report_date") or ""),
                "Subject": row.get("subject") or "",
                "Recipient": row.get("recipient") or "",
                "Sent": _format_timestamp(row.get("sent_at")),
                "Status": str(row.get("status") or "").title(),
                "Type": "TEST" if row.get("is_test") else "Production",
                "Provider ID": row.get("provider_message_id") or "",
                "Staff": int(summary.get("active_staff_count") or 0),
                "Actions": int(summary.get("total_actions") or 0),
                "Attention": "Yes" if int(summary.get("attention_count") or 0) else "No",
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)
    row_by_id = {row["id"]: row for row in rows}
    selected_id = st.selectbox(
        "Open report",
        tuple(row_by_id),
        format_func=lambda archive_id: _archive_label(row_by_id[archive_id]),
        key="reporting-open-archive",
    )
    try:
        archive = reporting_store.get_archive(user, selected_id)
        csv_download = reporting_store.archive_csv(user, selected_id)
    except PermissionError:
        st.error("Reporting access is not approved.")
        return
    except Exception:
        st.warning("This archived report could not be opened right now.")
        return
    st.download_button(
        "Download CSV",
        data=csv_download["content"],
        file_name=csv_download["filename"],
        mime="text/csv",
        key=f"reporting-download-csv::{selected_id}",
    )
    components.html(
        archive.get("html_snapshot") or "<p>Archived report content is unavailable.</p>",
        height=760,
        scrolling=True,
    )


def _render_delivery_health(user, digest_config, mail_config, storage_ready, now_utc):
    st.subheader("Delivery Health")
    public = mail_config.public_status()
    local_now = now_utc.astimezone(ZoneInfo(digest_config.timezone_name))
    next_send = daily_activity_reporting.next_expected_send(
        now_utc,
        configuration=digest_config,
    )
    rows = [
        ("Reports enabled", "Yes" if digest_config.enabled else "No"),
        ("Delivery configured", "Yes" if public["configured"] else "No"),
        ("Recipient", public["recipient"] or "Missing"),
        ("Sender", public["sender"] or "Missing"),
        ("Reply-to", public["reply_to"] or "Missing"),
        ("Report timezone", digest_config.timezone_name),
        ("Local send hour", f"{digest_config.send_hour:02d}:00"),
        ("Next expected send", next_send.strftime("%d %b %Y, %I:%M %p %Z")),
    ]
    st.dataframe(
        [{"Setting": label, "Value": value} for label, value in rows],
        use_container_width=True,
        hide_index=True,
    )
    if not public["configured"]:
        st.warning(" ".join(public["configuration_errors"]))
    if not storage_ready:
        return
    try:
        history = reporting_store.list_delivery_history(user, limit=10)
    except Exception:
        st.warning("Recent delivery history could not load right now.")
        return
    successes = [row for row in history if row.get("status") == "sent"]
    failures = [row for row in history if row.get("status") == "failed"]
    health_cols = st.columns(2)
    health_cols[0].metric(
        "Last successful report",
        _format_timestamp(successes[0].get("sent_at")) if successes else "None",
    )
    health_cols[1].metric(
        "Last sanitised failure",
        failures[0].get("sanitized_error") if failures else "None",
    )
    if history:
        st.dataframe(
            [
                {
                    "Date": str(row.get("report_date") or ""),
                    "Type": "TEST" if row.get("is_test") else "Production",
                    "Status": str(row.get("status") or "").title(),
                    "Attempts": int(row.get("attempt_count") or 0),
                    "Updated": _format_timestamp(row.get("updated_at")),
                }
                for row in history
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_test_email(user, storage_ready):
    st.subheader("Test Email")
    st.caption(
        "Sends a clearly labelled test with HTML, plain text, reply-to and a CSV attachment. "
        "It does not consume today's production report."
    )
    if not storage_ready:
        st.info("Apply the Reporting migration before sending a test.")
        return
    result = st.session_state.pop("reporting-test-result", None)
    if result:
        if result.get("ok"):
            st.success("Test email sent and archived.")
        else:
            st.warning(result.get("error") or "The test email could not be sent.")
    nonce = st.session_state.setdefault("reporting-test-nonce", uuid.uuid4().hex)
    if st.button(
        "Send test email",
        type="primary",
        disabled=bool(st.session_state.get("reporting-test-in-progress")),
        key="reporting-send-test-email",
    ):
        st.session_state["reporting-test-in-progress"] = True
        try:
            send_result = daily_activity_digest.send_test_daily_digest(
                user,
                nonce=nonce,
            )
        except PermissionError:
            send_result = {
                "ok": False,
                "status": "denied",
                "error": "Reporting access is not approved.",
            }
        except Exception:
            send_result = {
                "ok": False,
                "status": "failed",
                "error": "The test email could not be sent. Check Delivery Health.",
            }
        st.session_state["reporting-test-result"] = send_result
        st.session_state["reporting-test-in-progress"] = False
        st.rerun()


def render_page(user):
    if not os_accounts.can_access_reporting(user):
        st.title("Access not approved")
        st.caption("This page is not available for your account.")
        return

    now_utc = datetime.now(timezone.utc)
    digest_config = daily_activity_reporting.load_digest_configuration()
    mail_config = email_service.load_email_configuration()
    try:
        storage = reporting_store.schema_status()
    except Exception:
        storage = {"configured": True, "ready": False, "reason": "unavailable"}
    storage_ready = bool(storage.get("ready"))

    st.title("Reporting")
    snapshot = _render_today(
        user,
        now_utc,
        digest_config,
        mail_config,
        storage_ready,
    )
    _render_staff_summary(snapshot)
    _render_reporting_tables(user, now_utc)
    _render_sent_reports(user, storage_ready)
    _render_delivery_health(
        user,
        digest_config,
        mail_config,
        storage_ready,
        now_utc,
    )
    _render_test_email(user, storage_ready)


def render_weekly_review_page(user):
    if not sports_cave_dashboard.can_manage_daily_planner(user):
        st.title("Access not approved")
        st.caption("This page is not available for your account.")
        return
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(os_accounts.timezone_for_user(user) or "Australia/Sydney"))
    st.title("Reporting")
    st.subheader("Weekly Review")
    current_start, _current_end = sports_cave_dashboard.daily_execution_week_bounds(local_now.date())
    choice_cols = st.columns([1.8, 1])
    view = choice_cols[0].radio(
        "Review week",
        ("This week", "Last week", "Select week"),
        horizontal=True,
        label_visibility="collapsed",
        key="reporting-weekly-review-week-view",
    )
    if view == "Last week":
        week_start = current_start - timedelta(days=7)
    elif view == "Select week":
        anchor = choice_cols[1].date_input(
            "Week",
            value=current_start,
            label_visibility="collapsed",
            key="reporting-weekly-review-week-date",
        )
        week_start, _unused = sports_cave_dashboard.daily_execution_week_bounds(anchor)
    else:
        week_start = current_start
    week_end = week_start + timedelta(days=6)
    choice_cols[1].caption(f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}")
    try:
        weekly = sports_cave_dashboard.load_daily_execution_weekly_review(
            user, week_start, week_end, limit=1000
        )
        sheets = weekly["sheets"]
        timers = weekly["timers"]
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Weekly Review could not load right now.")
        return
    summary = sports_cave_dashboard.daily_execution_weekly_summary(
        sheets, timers, today=local_now.date()
    )
    try:
        week_plan_bundle = sports_cave_dashboard.load_daily_planner_week_plan(
            user, week_start
        )
    except sports_cave_dashboard.DashboardStorageError:
        week_plan_bundle = {"plan": {}, "execution": {}}
    week_plan = week_plan_bundle.get("plan") or {}
    if week_plan:
        st.markdown(
            f"**{week_plan.get('theme') or 'No weekly theme'}**  "
            f"{week_plan.get('quote_text') or ''}"
            + (f" - {week_plan.get('quote_author')}" if week_plan.get("quote_author") else "")
        )
        objective_rows = [
            {
                "Objective": objective.get("title") or "",
                "Measurable target": objective.get("measurable_target") or "",
                "Result": str(objective.get("result") or "Not reviewed").replace("_", " ").title(),
                "Tactics": len(objective.get("tactics") or []),
                "Completed tactics": sum(
                    str(tactic.get("status") or "") == "completed"
                    for tactic in objective.get("tactics") or []
                ),
            }
            for objective in week_plan.get("objectives") or []
        ]
        if objective_rows:
            st.dataframe(
                objective_rows,
                hide_index=True,
                use_container_width=True,
                height=min(180, 29 * (len(objective_rows) + 1)),
                row_height=28,
                key="reporting-weekly-plan-objectives",
            )
        st.caption(
            f"Weekly tactic execution: {round((week_plan_bundle.get('execution') or {}).get('percentage') or 0)}%"
        )
    metrics = st.columns(5)
    metrics[0].metric("Task completion", f"{round(summary['completion_percentage'])}%")
    metrics[1].metric("Completed", summary["completed"])
    metrics[2].metric("Did not finish", summary["did_not_finish"])
    metrics[3].metric("Skipped", summary["skipped"])
    metrics[4].metric("Remaining", summary["unresolved"])
    st.caption(
        f"{summary['completed']} of {summary['total_planned']} planned tasks completed | "
        f"Focused time: {sports_cave_dashboard.format_duration_seconds(summary['actual_focused_seconds'])} | "
        f"Days reviewed: {summary['days_reviewed']}"
    )
    st.markdown(f"**Biggest wins:** {'; '.join(summary['biggest_wins']) or 'No wins recorded yet.'}")
    st.markdown(f"**Main blockers:** {'; '.join(summary['main_blockers']) or 'No blockers recorded yet.'}")
    st.markdown(f"**Repeated unfinished work:** {'; '.join(summary['repeated_carryovers']) or 'None repeated this week.'}")
    staff_rows = [
        {
            "Staff": row.get("staff") or "",
            "Completion %": f"{round(float(row.get('completion_percentage') or 0))}%",
            "Completed": int(row.get("completed") or 0),
            "Did not finish": int(row.get("did_not_finish") or 0),
            "Skipped": int(row.get("skipped") or 0),
            "Remaining": int(row.get("unresolved") or 0),
            "Total planned": int(row.get("total_planned") or 0),
            "Focused time": sports_cave_dashboard.format_duration_seconds(row.get("actual_focused_seconds")),
        }
        for row in summary.get("staff_completion") or []
    ]
    if staff_rows:
        st.dataframe(
            staff_rows,
            hide_index=True,
            use_container_width=True,
            height=min(300, max(120, 28 * (len(staff_rows) + 1))),
            row_height=28,
            key="reporting-weekly-review-staff",
        )
    rows = []
    for sheet in sheets:
        rows.append(
            {
                "Date": sheet.get("sheet_date") or "",
                "Owner": sheet.get("user_name") or "",
                "Status": str(sheet.get("status") or "").title(),
                "Completion %": f"{round(sports_cave_dashboard.daily_execution_outcome_summary(sheet)['completion_percentage'])}%",
                "Tasks": sports_cave_dashboard.daily_execution_outcome_summary(sheet)["total_planned"],
                "Rating": ((sheet.get("ratings") or {}).get("Overall Score") or ""),
            }
        )
    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            height=min(360, max(220, 28 * (len(rows) + 1))),
            row_height=28,
            key="reporting-weekly-review-sheets",
        )
    else:
        st.caption("No Daily Planner records found for this week.")
