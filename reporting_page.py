import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import daily_activity_digest
import daily_activity_reporting
import email_service
import os_accounts
import reporting_store
import sports_cave_dashboard


ARCHIVE_PAGE_SIZE = 15
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
    for member in snapshot["staff"]:
        title = (
            f"{member['display_name']} | {member['role'].title()} | "
            f"{member['total_actions']} actions"
        )
        with st.expander(title, expanded=False):
            cols = st.columns(4)
            cols[0].metric("Meaningful", member["total_actions"])
            cols[1].metric("Completed", member["completed_actions"])
            cols[2].metric("Failed", member["failed_actions"])
            cols[3].metric(
                "Last activity",
                _format_timestamp(member.get("last_activity_at"), member.get("timezone"))
                if member.get("last_activity_at")
                else "None",
            )
            if member["work_lines"]:
                for line in member["work_lines"]:
                    st.write(f"- {line['label']}")
            else:
                st.caption("No recorded activity for this report period")
            if member.get("is_owner"):
                daily = member.get("daily_execution") or {}
                if not daily.get("exists"):
                    st.caption("Daily Execution: no sheet created for today.")
                else:
                    st.caption(
                        "Daily Execution: "
                        f"{daily['completed_count']} of {daily['task_count']} closed "
                        f"({daily['completion_percentage']}%)."
                    )
            social = member.get("social_media") or {}
            if social:
                st.caption(
                    "Social Media: "
                    f"{str(social.get('plan_status') or 'not_started').replace('_', ' ').title()} | "
                    f"{int(social.get('mips_completed') or 0)} MIPs complete | "
                    f"{int(social.get('posts_live') or 0)} posts live | "
                    f"{float(social.get('score') or 0):.1f}/10"
                )
                if social.get("weekly_headline"):
                    st.caption(f"Latest weekly check-in: {social['weekly_headline']}")


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
    try:
        rows = sports_cave_dashboard.list_daily_execution_history(
            user,
            start_date,
            end_date,
            limit=5000,
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Daily Execution history could not load right now.")
        return
    if not rows:
        st.caption("No Daily Planner tasks found for this period.")
        return
    table_rows = []
    for row in rows:
        timer = row.get("timer") or {}
        actual_elapsed = timer.get("actual_elapsed_seconds") or timer.get("elapsed_seconds")
        table_rows.append(
            {
                "Work date": row.get("work_date") or "",
                "Task": row.get("task") or "",
                "Owner": row.get("owner") or "",
                "Category/area": row.get("category") or "",
                "Allocated duration": row.get("allocated") or sports_cave_dashboard.format_duration_seconds(row.get("allocated_seconds")),
                "Actual elapsed": sports_cave_dashboard.format_duration_seconds(actual_elapsed),
                "Start time": _timer_timestamp(timer, "started_at", user),
                "End time": _timer_timestamp(timer, "outcome_at", user) or _format_timestamp(row.get("completed_at") or row.get("finished_at"), os_accounts.timezone_for_user(user)),
                "Status": row.get("status") or "Planned",
                "Outcome": _outcome_display(row.get("outcome") or timer.get("outcome")),
                "Notes": row.get("notes") or "",
                "_row_id": row.get("row_id") or "",
            }
        )
    st.caption(f"{len(table_rows)} task record(s) in range")
    st.dataframe(
        table_rows,
        hide_index=True,
        use_container_width=True,
        height=min(520, max(360, 28 * (len(table_rows) + 1))),
        row_height=28,
        column_order=(
            "Work date",
            "Task",
            "Owner",
            "Category/area",
            "Allocated duration",
            "Actual elapsed",
            "Start time",
            "End time",
            "Status",
            "Outcome",
            "Notes",
        ),
        key="reporting-daily-execution-history",
    )


def _outcome_display(value):
    clean = str(value or "").strip().casefold()
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_COMPLETED:
        return "Completed"
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_DID_NOT_FINISH:
        return "Did not finish"
    return ""


def _render_operational_activity(user, local_now, start_date, end_date):
    if not os_accounts.can_view_activity_log(user):
        return
    st.subheader("Recent Operational Activity")
    try:
        entries = sports_cave_dashboard.list_activity_entries(
            sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
            local_now,
            limit=None,
            user=user,
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Operational activity could not load right now.")
        return
    timezone_name = os_accounts.timezone_for_user(user) or daily_activity_reporting.REPORT_TIMEZONE
    try:
        tzinfo = ZoneInfo(timezone_name)
    except Exception:
        tzinfo = daily_activity_reporting.SYDNEY_TZ
    filtered = []
    for entry in entries:
        created = entry.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None
        if isinstance(created, datetime):
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            local_date = created.astimezone(tzinfo).date()
            if not (start_date <= local_date <= end_date):
                continue
        filtered.append(entry)
    if not filtered:
        st.caption("No meaningful operational activity found for this period.")
        return
    records = [
        sports_cave_dashboard.activity_table_record(entry, tzinfo)
        for entry in sports_cave_dashboard.group_mockup_activity_entries(filtered, tzinfo)
    ]
    st.dataframe(
        records,
        hide_index=True,
        use_container_width=True,
        height=min(430, max(260, 28 * (len(records) + 1))),
        row_height=28,
        key="reporting-operational-activity",
    )


def _render_reporting_tables(user, now_utc):
    local_now = now_utc.astimezone(ZoneInfo(os_accounts.timezone_for_user(user) or daily_activity_reporting.REPORT_TIMEZONE))
    start_date, end_date, _label = _period_bounds(user)
    _render_daily_execution_history(user, start_date, end_date)
    _render_operational_activity(user, local_now, start_date, end_date)


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
        sheets = sports_cave_dashboard.list_daily_execution_archive_summaries(
            user,
            week_start,
            week_end,
            limit=31,
        )
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Weekly Review could not load right now.")
        return
    summary = sports_cave_dashboard.daily_execution_weekly_summary(sheets)
    metrics = st.columns(4)
    metrics[0].metric("Days planned", summary["days_planned"])
    metrics[1].metric("Days reviewed", summary["days_reviewed"])
    metrics[2].metric("MIPs completed", summary["mip_completed"])
    metrics[3].metric("Average rating", summary["average_day_rating"] or "-")
    st.caption(
        f"MIPs not completed: {summary['mip_not_completed']} | Other tasks completed: {summary['other_completed']} | Planned hours: {summary['planned_hours']}"
    )
    st.markdown(f"**Biggest wins:** {'; '.join(summary['biggest_wins']) or 'No wins recorded yet.'}")
    st.markdown(f"**Main blockers:** {'; '.join(summary['main_blockers']) or 'No blockers recorded yet.'}")
    st.markdown(f"**Repeated unfinished work:** {'; '.join(summary['repeated_carryovers']) or 'None repeated this week.'}")
    rows = []
    for sheet in sheets:
        rows.append(
            {
                "Date": sheet.get("sheet_date") or "",
                "Owner": sheet.get("user_name") or "",
                "Status": str(sheet.get("status") or "").title(),
                "MIPs closed": sports_cave_dashboard.daily_execution_completed_count(sheet),
                "Tasks": sports_cave_dashboard.daily_execution_filled_task_count(sheet),
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
