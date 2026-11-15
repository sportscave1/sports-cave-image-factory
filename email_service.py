import base64
import os
import time
from dataclasses import dataclass, field
from email.utils import parseaddr

import requests


RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_ATTEMPTS = 3
TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    def __init__(self, safe_message, *, retryable=False, status_code=None, attempts=1):
        super().__init__(safe_message)
        self.safe_message = str(safe_message or "Email delivery failed.")
        self.retryable = bool(retryable)
        self.status_code = status_code
        self.attempts = max(int(attempts or 1), 1)


@dataclass(frozen=True)
class EmailConfiguration:
    api_key: str = field(repr=False)
    sender: str = ""
    recipient: str = ""
    reply_to: str = ""
    provider: str = "resend"

    def validation_errors(self):
        errors = []
        if self.provider != "resend":
            errors.append("Only Resend delivery is supported.")
        if not str(self.api_key or "").strip():
            errors.append("RESEND_API_KEY is missing.")
        if not _valid_mailbox(self.sender):
            errors.append("ACTIVITY_DIGEST_FROM is missing or invalid.")
        if not _valid_mailbox(self.recipient):
            errors.append("ACTIVITY_DIGEST_TO is missing or invalid.")
        if self.reply_to and not _valid_mailbox(self.reply_to):
            errors.append("ACTIVITY_DIGEST_REPLY_TO is invalid.")
        return errors

    @property
    def configured(self):
        return not self.validation_errors()

    def public_status(self):
        return {
            "provider": self.provider,
            "configured": self.configured,
            "sender": self.sender,
            "recipient": self.recipient,
            "reply_to": self.reply_to,
            "api_key_present": bool(str(self.api_key or "").strip()),
            "configuration_errors": self.validation_errors(),
        }


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes


@dataclass(frozen=True)
class EmailMessage:
    subject: str
    html: str
    text: str
    attachments: tuple = ()


@dataclass(frozen=True)
class EmailDeliveryResult:
    provider: str
    provider_message_id: str
    attempts: int


def _valid_mailbox(value):
    _name, address = parseaddr(str(value or "").strip())
    return bool(address and "@" in address and not any(char.isspace() for char in address))


def load_email_configuration(environ=None):
    environ = os.environ if environ is None else environ
    return EmailConfiguration(
        api_key=str(environ.get("RESEND_API_KEY", "") or "").strip(),
        sender=str(environ.get("ACTIVITY_DIGEST_FROM", "") or "").strip(),
        recipient=str(environ.get("ACTIVITY_DIGEST_TO", "") or "").strip(),
        reply_to=str(environ.get("ACTIVITY_DIGEST_REPLY_TO", "") or "").strip(),
    )


def _safe_provider_error(status_code, error_type=""):
    clean_type = str(error_type or "").strip().casefold()
    if clean_type == "concurrent_idempotent_requests":
        return "An identical email request is still being processed."
    if clean_type == "invalid_idempotent_request":
        return "The email duplicate-protection key was rejected."
    if clean_type in {"invalid_api_key", "restricted_api_key"} or status_code in {401, 403}:
        return "Email delivery is not authorised. Check the Resend configuration."
    if status_code == 429:
        return "Email delivery is temporarily rate limited."
    if status_code and status_code >= 500:
        return "The email provider is temporarily unavailable."
    if status_code in {400, 404, 405, 409, 422}:
        return "The email provider rejected the delivery request."
    return "Email delivery failed."


def _response_error_type(response):
    try:
        payload = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("name") or payload.get("error") or "").strip()


class ResendEmailProvider:
    def __init__(
        self,
        configuration,
        *,
        session=None,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        sleeper=time.sleep,
    ):
        self.configuration = configuration
        self.session = session or requests.Session()
        self.timeout_seconds = max(float(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), 1)
        self.max_attempts = min(max(int(max_attempts or DEFAULT_MAX_ATTEMPTS), 1), 5)
        self.sleeper = sleeper

    def _payload(self, message):
        payload = {
            "from": self.configuration.sender,
            "to": [self.configuration.recipient],
            "subject": str(message.subject or "").strip(),
            "html": str(message.html or ""),
            "text": str(message.text or ""),
        }
        if self.configuration.reply_to:
            payload["reply_to"] = self.configuration.reply_to
        attachments = []
        for attachment in message.attachments or ():
            filename = str(attachment.filename or "report.csv").strip() or "report.csv"
            attachments.append(
                {
                    "filename": filename[:240],
                    "content": base64.b64encode(bytes(attachment.content or b"")).decode("ascii"),
                }
            )
        if attachments:
            payload["attachments"] = attachments
        return payload

    def send(self, message, *, idempotency_key):
        errors = self.configuration.validation_errors()
        if errors:
            raise EmailConfigurationError(" ".join(errors))
        clean_key = str(idempotency_key or "").strip()
        if not clean_key or len(clean_key) > 256:
            raise EmailConfigurationError("A valid email idempotency key is required.")

        payload = self._payload(message)
        headers = {
            "Authorization": f"Bearer {self.configuration.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": clean_key,
        }
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.post(
                    RESEND_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException:
                last_error = EmailDeliveryError(
                    "The email provider could not be reached.",
                    retryable=True,
                    attempts=attempt,
                )
            else:
                if 200 <= int(response.status_code) < 300:
                    try:
                        provider_message_id = str((response.json() or {}).get("id") or "").strip()
                    except Exception:
                        provider_message_id = ""
                    if not provider_message_id:
                        raise EmailDeliveryError(
                            "The email provider returned an incomplete success response.",
                            retryable=False,
                            status_code=response.status_code,
                            attempts=attempt,
                        )
                    return EmailDeliveryResult(
                        provider="resend",
                        provider_message_id=provider_message_id[:250],
                        attempts=attempt,
                    )

                error_type = _response_error_type(response)
                retryable = (
                    int(response.status_code) in TRANSIENT_STATUS_CODES
                    or error_type == "concurrent_idempotent_requests"
                )
                last_error = EmailDeliveryError(
                    _safe_provider_error(response.status_code, error_type),
                    retryable=retryable,
                    status_code=response.status_code,
                    attempts=attempt,
                )

            if not last_error.retryable or attempt >= self.max_attempts:
                raise last_error
            self.sleeper(min(0.25 * (2 ** (attempt - 1)), 1.0))

        raise last_error or EmailDeliveryError("Email delivery failed.")


class EmailService:
    def __init__(self, configuration=None, *, provider=None):
        self.configuration = configuration or load_email_configuration()
        self.provider = provider or ResendEmailProvider(self.configuration)

    def send(self, message, *, idempotency_key):
        return self.provider.send(message, idempotency_key=idempotency_key)
