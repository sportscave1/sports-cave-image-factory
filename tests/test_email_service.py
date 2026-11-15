import base64
import unittest

import requests

import email_service


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def configuration(api_key="re_test_secret"):
    return email_service.EmailConfiguration(
        api_key=api_key,
        sender="Sports Cave OS <daily@reports.sportscave.test>",
        recipient="owner@sportscave.test",
        reply_to="reply@sportscave.test",
    )


def message():
    return email_service.EmailMessage(
        subject="Daily report",
        html="<p>HTML report</p>",
        text="Plain report",
        attachments=(
            email_service.EmailAttachment("report.csv", b"one,two\n1,2\n"),
        ),
    )


class EmailServiceTests(unittest.TestCase):
    def test_success_sends_html_text_reply_to_attachment_and_idempotency(self):
        session = FakeSession([FakeResponse(200, {"id": "email-1"})])
        provider = email_service.ResendEmailProvider(
            configuration(),
            session=session,
            sleeper=lambda _seconds: None,
        )

        result = provider.send(message(), idempotency_key="daily/2026-07-28")

        self.assertEqual(result.provider_message_id, "email-1")
        self.assertEqual(result.attempts, 1)
        url, request = session.calls[0]
        self.assertEqual(url, email_service.RESEND_API_URL)
        self.assertEqual(request["headers"]["Idempotency-Key"], "daily/2026-07-28")
        self.assertTrue(request["headers"]["Authorization"].startswith("Bearer "))
        self.assertEqual(request["json"]["html"], "<p>HTML report</p>")
        self.assertEqual(request["json"]["text"], "Plain report")
        self.assertEqual(request["json"]["reply_to"], "reply@sportscave.test")
        self.assertEqual(
            base64.b64decode(request["json"]["attachments"][0]["content"]),
            b"one,two\n1,2\n",
        )

    def test_transient_failure_retries_with_same_provider_idempotency_key(self):
        session = FakeSession(
            [
                FakeResponse(503, {"name": "application_error"}),
                FakeResponse(200, {"id": "email-2"}),
            ]
        )
        provider = email_service.ResendEmailProvider(
            configuration(),
            session=session,
            max_attempts=3,
            sleeper=lambda _seconds: None,
        )

        result = provider.send(message(), idempotency_key="daily/2026-07-28")

        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(
            session.calls[0][1]["headers"]["Idempotency-Key"],
            session.calls[1][1]["headers"]["Idempotency-Key"],
        )

    def test_network_failure_is_bounded_and_sanitised(self):
        session = FakeSession(
            [
                requests.ConnectionError("secret host details"),
                requests.Timeout("secret timeout details"),
            ]
        )
        provider = email_service.ResendEmailProvider(
            configuration(),
            session=session,
            max_attempts=2,
            sleeper=lambda _seconds: None,
        )

        with self.assertRaises(email_service.EmailDeliveryError) as captured:
            provider.send(message(), idempotency_key="daily/2026-07-28")

        self.assertTrue(captured.exception.retryable)
        self.assertEqual(captured.exception.attempts, 2)
        self.assertNotIn("secret", captured.exception.safe_message)

    def test_permanent_failure_does_not_retry_or_expose_provider_response(self):
        session = FakeSession(
            [
                FakeResponse(
                    403,
                    {
                        "name": "invalid_api_key",
                        "message": "The leaked key is re_private",
                    },
                )
            ]
        )
        provider = email_service.ResendEmailProvider(
            configuration(),
            session=session,
            sleeper=lambda _seconds: None,
        )

        with self.assertRaises(email_service.EmailDeliveryError) as captured:
            provider.send(message(), idempotency_key="daily/2026-07-28")

        self.assertFalse(captured.exception.retryable)
        self.assertEqual(len(session.calls), 1)
        self.assertNotIn("re_private", captured.exception.safe_message)

    def test_missing_configuration_fails_before_network(self):
        session = FakeSession([])
        provider = email_service.ResendEmailProvider(
            configuration(api_key=""),
            session=session,
        )

        with self.assertRaises(email_service.EmailConfigurationError):
            provider.send(message(), idempotency_key="daily/2026-07-28")

        self.assertEqual(session.calls, [])

    def test_public_configuration_status_never_contains_api_key(self):
        public = configuration().public_status()

        self.assertTrue(public["api_key_present"])
        self.assertNotIn("api_key", public)
        self.assertNotIn("re_test_secret", str(public))


if __name__ == "__main__":
    unittest.main()
