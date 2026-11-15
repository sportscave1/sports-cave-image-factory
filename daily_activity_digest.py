from datetime import datetime, timezone

import daily_activity_reporting
import email_service
import os_accounts
import reporting_store
from activity_log import record_activity_log


class DailyDigestError(RuntimeError):
    pass


def _message_from_archive(archive):
    return email_service.EmailMessage(
        subject=str(archive.get("subject") or ""),
        html=str(archive.get("html_snapshot") or ""),
        text=str(archive.get("text_snapshot") or ""),
        attachments=(
            email_service.EmailAttachment(
                filename=str(archive.get("csv_filename") or "sports-cave-report.csv"),
                content=str(archive.get("csv_content") or "").encode("utf-8-sig"),
            ),
        ),
    )


def _log_test_action(actor, claim, *, status, safe_error=""):
    delivery = claim.get("delivery") or {}
    delivery_id = str(delivery.get("id") or "")
    if not delivery_id:
        return
    successful = str(status or "").casefold() in {"sent", "already_sent"}
    record_activity_log(
        "reporting_test_email_sent" if successful else "reporting_test_email_failed",
        "Reporting",
        "Reporting test email sent" if successful else "Reporting test email failed",
        entity_type="activity_report_delivery",
        entity_id=delivery_id,
        metadata={
            "status": "success" if successful else "failed",
            "result": "success" if successful else "failed",
            "test": True,
            "safe_error": str(safe_error or "")[:250],
            "actor_id": (actor or {}).get("id") or "",
        },
        event_key=f"reporting-test-email:{delivery_id}",
    )


def _deliver_claimed_report(
    claim,
    *,
    service,
    store=reporting_store,
    actor=None,
    is_test=False,
):
    delivery = claim.get("delivery") or {}
    archive = claim.get("archive") or {}
    if not claim.get("should_send"):
        status = str(claim.get("status") or "skipped")
        if is_test and status in {"already_sent", "permanent_failure"}:
            _log_test_action(
                actor,
                claim,
                status=status,
                safe_error=delivery.get("sanitized_error") or "",
            )
        return {
            "ok": status == "already_sent",
            "status": status,
            "delivery_id": str(delivery.get("id") or ""),
            "provider_message_id": str(delivery.get("provider_message_id") or ""),
            "sent": False,
        }

    message = _message_from_archive(archive)
    try:
        result = service.send(
            message,
            idempotency_key=str(delivery.get("idempotency_key") or ""),
        )
    except email_service.EmailConfigurationError as error:
        safe_error = str(error)
        store.mark_delivery_failed(
            delivery.get("id"),
            sanitized_error=safe_error,
            retryable=False,
            provider_attempts=1,
        )
        if is_test:
            _log_test_action(actor, claim, status="failed", safe_error=safe_error)
        return {
            "ok": False,
            "status": "failed",
            "delivery_id": str(delivery.get("id") or ""),
            "error": safe_error,
            "retryable": False,
            "sent": False,
        }
    except email_service.EmailDeliveryError as error:
        store.mark_delivery_failed(
            delivery.get("id"),
            sanitized_error=error.safe_message,
            retryable=error.retryable,
            provider_attempts=error.attempts,
        )
        if is_test:
            _log_test_action(
                actor,
                claim,
                status="failed",
                safe_error=error.safe_message,
            )
        return {
            "ok": False,
            "status": "failed",
            "delivery_id": str(delivery.get("id") or ""),
            "error": error.safe_message,
            "retryable": error.retryable,
            "sent": False,
        }

    saved = store.mark_delivery_sent(
        delivery.get("id"),
        provider_message_id=result.provider_message_id,
        provider_attempts=result.attempts,
    )
    final_delivery = saved.get("delivery") or delivery
    if is_test:
        _log_test_action(actor, claim, status="sent")
    return {
        "ok": True,
        "status": "sent",
        "delivery_id": str(final_delivery.get("id") or ""),
        "provider_message_id": result.provider_message_id,
        "attempts": result.attempts,
        "sent": True,
    }


def preview_daily_digest(
    *,
    now=None,
    report_date=None,
    account_store=None,
    backend=None,
    environ=None,
):
    now_utc = now or datetime.now(timezone.utc)
    digest_config = daily_activity_reporting.load_digest_configuration(environ)
    mail_config = email_service.load_email_configuration(environ)
    period = daily_activity_reporting.build_report_period(
        now_utc,
        timezone_name=digest_config.timezone_name,
        report_date=report_date,
    )
    snapshot = daily_activity_reporting.collect_report_snapshot(
        period=period,
        account_store=account_store,
        backend=backend,
        recipient=mail_config.recipient,
        is_test=False,
        owner_email=os_accounts.reporting_owner_email(environ),
    )
    return {
        "ok": True,
        "status": "preview",
        "preview": True,
        "snapshot": snapshot,
        "sent": False,
    }


def run_production_daily_digest(
    *,
    now=None,
    account_store=None,
    backend=None,
    store=reporting_store,
    service=None,
    environ=None,
):
    now_utc = now or datetime.now(timezone.utc)
    digest_config = daily_activity_reporting.load_digest_configuration(environ)
    should_run, reason, report_date = daily_activity_reporting.production_run_decision(
        now_utc,
        configuration=digest_config,
    )
    if not should_run:
        return {
            "ok": True,
            "status": reason,
            "report_date": report_date.isoformat(),
            "sent": False,
        }

    mail_config = email_service.load_email_configuration(environ)
    config_errors = mail_config.validation_errors()
    if config_errors:
        return {
            "ok": False,
            "status": "configuration_error",
            "error": " ".join(config_errors),
            "report_date": report_date.isoformat(),
            "sent": False,
        }

    period = daily_activity_reporting.build_report_period(
        now_utc,
        timezone_name=digest_config.timezone_name,
    )
    snapshot = daily_activity_reporting.collect_report_snapshot(
        period=period,
        account_store=account_store,
        backend=backend,
        recipient=mail_config.recipient,
        is_test=False,
        owner_email=os_accounts.reporting_owner_email(environ),
    )
    idempotency_key = daily_activity_reporting.deterministic_idempotency_key(snapshot)
    claim = store.claim_delivery(snapshot, idempotency_key=idempotency_key)
    delivery_service = service or email_service.EmailService(mail_config)
    result = _deliver_claimed_report(
        claim,
        service=delivery_service,
        store=store,
        is_test=False,
    )
    result["report_date"] = report_date.isoformat()
    return result


def send_test_daily_digest(
    actor,
    *,
    nonce,
    now=None,
    account_store=None,
    backend=None,
    store=reporting_store,
    service=None,
    environ=None,
):
    if not os_accounts.can_access_reporting(actor):
        raise PermissionError("Reporting access is not approved.")
    clean_nonce = str(nonce or "").strip()
    if not clean_nonce:
        raise ValueError("A test-email request key is required.")
    now_utc = now or datetime.now(timezone.utc)
    digest_config = daily_activity_reporting.load_digest_configuration(environ)
    mail_config = email_service.load_email_configuration(environ)
    config_errors = mail_config.validation_errors()
    if config_errors:
        return {
            "ok": False,
            "status": "configuration_error",
            "error": " ".join(config_errors),
            "sent": False,
        }
    period = daily_activity_reporting.build_report_period(
        now_utc,
        timezone_name=digest_config.timezone_name,
    )
    snapshot = daily_activity_reporting.collect_report_snapshot(
        period=period,
        account_store=account_store,
        backend=backend,
        recipient=mail_config.recipient,
        is_test=True,
        owner_email=os_accounts.reporting_owner_email(environ),
    )
    idempotency_key = daily_activity_reporting.deterministic_idempotency_key(
        snapshot,
        nonce=clean_nonce,
    )
    claim = store.claim_delivery(snapshot, idempotency_key=idempotency_key)
    delivery_service = service or email_service.EmailService(mail_config)
    return _deliver_claimed_report(
        claim,
        service=delivery_service,
        store=store,
        actor=actor,
        is_test=True,
    )
