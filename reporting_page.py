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


ARCHIVE_PAGE_SIZE = 15


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
    _render_sent_reports(user, storage_ready)
    _render_delivery_health(
        user,
        digest_config,
        mail_config,
        storage_ready,
        now_utc,
    )
    _render_test_email(user, storage_ready)
