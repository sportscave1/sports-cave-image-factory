import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import daily_activity_digest
import email_service
import os_accounts


OWNER_EMAIL = "owner@sportscave.test"
NOW = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)


class FakeAccountStore:
    def __init__(self):
        self.calls = 0
        self.users = [
            {
                "id": "owner-1",
                "username": "owner",
                "email": OWNER_EMAIL,
                "display_name": "Nathan",
                "role": "admin",
                "country": "Australia",
                "timezone": "Australia/Sydney",
                "is_active": True,
                "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
            },
            {
                "id": "worker-1",
                "username": "worker",
                "email": "worker@sportscave.test",
                "display_name": "Worker",
                "role": "worker",
                "country": "Philippines",
                "timezone": "Asia/Manila",
                "is_active": True,
                "page_permissions": ["dashboard"],
            },
        ]

    def list_users(self):
        self.calls += 1
        return [dict(user) for user in self.users]


class FakeBackend:
    def __init__(self):
        self.activity_calls = []
        self.daily_calls = []

    def list_activity_logs(self, *, start_at, end_at, limit):
        self.activity_calls.append((start_at, end_at, limit))
        return [
            {
                "id": "activity-1",
                "event_type": "files_uploaded",
                "activity_action_type": "files_uploaded",
                "activity_message": "Uploaded file: one.jpg",
                "activity_page": "Files",
                "activity_metadata": {
                    "actor_id": "worker-1",
                    "actor_display": "Worker",
                    "source_user_initiated": True,
                    "status": "success",
                },
                "actor": "Worker",
                "source": "Files",
                "created_at": NOW - timedelta(hours=2),
            }
        ]

    def get_daily_execution_sheet(self, user_id, report_date):
        self.daily_calls.append((user_id, report_date))
        return {
            "user_id": user_id,
            "sheet_date": report_date,
            "status": "active",
            "top_tasks": [{"task": "Owner task", "status": "done"}],
            "additional_items": [],
        }


class MemoryDeliveryStore:
    def __init__(self):
        self.rows = {}
        self.claims = []
        self.failures = []

    def claim_delivery(self, snapshot, *, idempotency_key):
        self.claims.append((snapshot, idempotency_key))
        existing = self.rows.get(idempotency_key)
        if existing:
            return {
                "status": "already_sent" if existing["delivery"]["status"] == "sent" else "in_progress",
                "should_send": False,
                **existing,
            }
        delivery = {
            "id": f"delivery-{len(self.rows) + 1}",
            "status": "pending",
            "idempotency_key": idempotency_key,
            "provider_message_id": "",
        }
        archive = {
            "subject": snapshot["subject"],
            "html_snapshot": snapshot["html"],
            "text_snapshot": snapshot["text"],
            "csv_filename": snapshot["csv_filename"],
            "csv_content": snapshot["csv_content"],
        }
        row = {"delivery": delivery, "archive": archive}
        self.rows[idempotency_key] = row
        return {"status": "claimed", "should_send": True, **row}

    def mark_delivery_sent(self, delivery_id, *, provider_message_id, provider_attempts=1):
        for row in self.rows.values():
            if row["delivery"]["id"] == delivery_id:
                row["delivery"].update(
                    status="sent",
                    provider_message_id=provider_message_id,
                )
                return row
        raise AssertionError("missing delivery")

    def mark_delivery_failed(
        self,
        delivery_id,
        *,
        sanitized_error,
        retryable,
        provider_attempts=1,
    ):
        self.failures.append((delivery_id, sanitized_error, retryable, provider_attempts))
        for row in self.rows.values():
            if row["delivery"]["id"] == delivery_id:
                row["delivery"]["status"] = "failed"
                return row
        raise AssertionError("missing delivery")


class FakeEmailService:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def send(self, message, *, idempotency_key):
        self.calls.append((message, idempotency_key))
        if self.failure:
            raise self.failure
        return email_service.EmailDeliveryResult(
            provider="resend",
            provider_message_id="provider-1",
            attempts=1,
        )


def environment(*, enabled="true", api_key="re_test"):
    return {
        "ACTIVITY_DIGEST_ENABLED": enabled,
        "ACTIVITY_DIGEST_TIMEZONE": "Australia/Sydney",
        "ACTIVITY_DIGEST_HOUR": "17",
        "ACTIVITY_DIGEST_FROM": "Sports Cave OS <daily@reports.sportscave.test>",
        "ACTIVITY_DIGEST_TO": "owner@sportscave.test",
        "ACTIVITY_DIGEST_REPLY_TO": "reply@sportscave.test",
        "RESEND_API_KEY": api_key,
        "SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL,
    }


class DailyDigestTests(unittest.TestCase):
    def test_disabled_run_exits_successfully_without_queries_or_delivery(self):
        accounts = FakeAccountStore()
        backend = FakeBackend()
        store = MemoryDeliveryStore()
        service = FakeEmailService()

        result = daily_activity_digest.run_production_daily_digest(
            now=NOW,
            account_store=accounts,
            backend=backend,
            store=store,
            service=service,
            environ=environment(enabled="false"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(accounts.calls, 0)
        self.assertEqual(backend.activity_calls, [])
        self.assertEqual(service.calls, [])

    def test_missing_configuration_fails_before_report_queries(self):
        accounts = FakeAccountStore()
        backend = FakeBackend()

        result = daily_activity_digest.run_production_daily_digest(
            now=NOW,
            account_store=accounts,
            backend=backend,
            store=MemoryDeliveryStore(),
            service=FakeEmailService(),
            environ=environment(api_key=""),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "configuration_error")
        self.assertIn("RESEND_API_KEY", result["error"])
        self.assertEqual(accounts.calls, 0)

    def test_success_queries_only_current_utc_range_and_persists_delivery(self):
        accounts = FakeAccountStore()
        backend = FakeBackend()
        store = MemoryDeliveryStore()
        service = FakeEmailService()

        result = daily_activity_digest.run_production_daily_digest(
            now=NOW,
            account_store=accounts,
            backend=backend,
            store=store,
            service=service,
            environ=environment(),
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["sent"])
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(backend.activity_calls), 1)
        start_at, end_at, limit = backend.activity_calls[0]
        self.assertEqual(start_at, datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc))
        self.assertEqual(end_at, NOW)
        self.assertIsNone(limit)
        self.assertEqual(backend.daily_calls, [("owner-1", "2026-07-28")])
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(len(service.calls), 1)
        sent_message = service.calls[0][0]
        self.assertIn("Nathan", sent_message.html)
        self.assertIn("Worker", sent_message.text)
        self.assertEqual(len(sent_message.attachments), 1)

    def test_duplicate_hourly_execution_sends_production_report_once(self):
        accounts = FakeAccountStore()
        backend = FakeBackend()
        store = MemoryDeliveryStore()
        service = FakeEmailService()
        arguments = {
            "now": NOW,
            "account_store": accounts,
            "backend": backend,
            "store": store,
            "service": service,
            "environ": environment(),
        }

        first = daily_activity_digest.run_production_daily_digest(**arguments)
        second = daily_activity_digest.run_production_daily_digest(**arguments)

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "already_sent")
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(len(store.rows), 1)

    def test_retryable_failure_is_recorded_without_false_success(self):
        failure = email_service.EmailDeliveryError(
            "The email provider is temporarily unavailable.",
            retryable=True,
            attempts=3,
        )
        store = MemoryDeliveryStore()
        result = daily_activity_digest.run_production_daily_digest(
            now=NOW,
            account_store=FakeAccountStore(),
            backend=FakeBackend(),
            store=store,
            service=FakeEmailService(failure=failure),
            environ=environment(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["retryable"])
        self.assertEqual(store.failures[0][2:], (True, 3))

    def test_test_email_uses_separate_key_and_duplicate_log_event_key(self):
        actor = FakeAccountStore().users[0]
        store = MemoryDeliveryStore()
        service = FakeEmailService()
        with patch.dict(os.environ, environment(), clear=False), patch.object(
            daily_activity_digest,
            "record_activity_log",
        ) as record:
            first = daily_activity_digest.send_test_daily_digest(
                actor,
                nonce="button-request-1",
                now=NOW,
                account_store=FakeAccountStore(),
                backend=FakeBackend(),
                store=store,
                service=service,
                environ=environment(),
            )
            second = daily_activity_digest.send_test_daily_digest(
                actor,
                nonce="button-request-1",
                now=NOW,
                account_store=FakeAccountStore(),
                backend=FakeBackend(),
                store=store,
                service=service,
                environ=environment(),
            )

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "already_sent")
        self.assertEqual(len(service.calls), 1)
        self.assertTrue(service.calls[0][0].subject.startswith("[TEST]"))
        self.assertIn("/test", next(iter(store.rows)).replace("sports-cave-test", "/test"))
        event_keys = [call.kwargs["event_key"] for call in record.call_args_list]
        self.assertEqual(len(set(event_keys)), 1)
        self.assertTrue(event_keys[0].startswith("reporting-test-email:delivery-"))

    def test_preview_historical_date_never_sends_or_claims_delivery(self):
        accounts = FakeAccountStore()
        backend = FakeBackend()
        result = daily_activity_digest.preview_daily_digest(
            now=NOW,
            report_date="2026-07-27",
            account_store=accounts,
            backend=backend,
            environ=environment(),
        )

        self.assertTrue(result["preview"])
        self.assertFalse(result["sent"])
        self.assertEqual(result["snapshot"]["report_date"], "2026-07-27")


if __name__ == "__main__":
    unittest.main()
