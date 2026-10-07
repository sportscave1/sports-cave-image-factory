"""Explicit SMTP submission and in-process send receipts. No automatic retries or import I/O."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import logging
import os
import smtplib
import ssl
from threading import Lock
import uuid
import time

from support_email_provider import MailboxError

LOGGER = logging.getLogger(__name__)


def report_progress(callback, percent, label):
    """Display-only hooks must never change a delivery outcome or trigger a retry."""
    if callback:
        try:
            callback(percent, label)
        except Exception:
            LOGGER.warning("Email progress display unavailable")


@dataclass(frozen=True)
class SMTPConfiguration:
    host: str = "ventraip.email"
    port: int = 465
    address: str = "hello@sportscaveshop.com"
    password: str = field(default="", repr=False)
    use_ssl: bool = True
    timeout: float = 12
    data_timeout: float = 120

    @property
    def configured(self):
        return bool(self.host and self.port == 465 and self.use_ssl and self.password and "@" in self.address)


def load_smtp_configuration(environ=None):
    env = os.environ if environ is None else environ
    try:
        port = int(env.get("SPORTSCAVE_EMAIL_SMTP_PORT", "465"))
    except (ValueError, TypeError):
        port = 0
    return SMTPConfiguration(host=env.get("SPORTSCAVE_EMAIL_SMTP_HOST", "ventraip.email").strip(), port=port,
        address=env.get("SPORTSCAVE_EMAIL_SMTP_ADDRESS", "hello@sportscaveshop.com").strip(),
        password=env.get("SPORTSCAVE_EMAIL_SMTP_PASSWORD", ""),
        use_ssl=env.get("SPORTSCAVE_EMAIL_SMTP_SSL", "true").casefold() == "true")


class SMTPProvider:
    def __init__(self, configuration, *, connection_factory=None):
        self.configuration = configuration
        self.connection_factory = connection_factory or smtplib.SMTP_SSL

    def submit(self, mime, *, mailbox, progress=None):
        cfg, conn, data_started = self.configuration, None, False
        started=time.monotonic()
        if not cfg.configured or cfg.address.casefold() != mailbox.casefold():
            return {"status": "rejected", "notice": "SMTP is not configured for this mailbox."}
        try:
            report_progress(progress, 45, "Connecting securely…")
            conn = self.connection_factory(cfg.host, cfg.port, context=ssl.create_default_context(), timeout=cfg.timeout)
            conn.set_debuglevel(0)
            code, _ = conn.ehlo()
            if code != 250:
                raise smtplib.SMTPException("EHLO rejected")
            report_progress(progress, 60, "Authenticating mail server…")
            conn.login(cfg.address, cfg.password)
            maximum = str(getattr(conn, "esmtp_features", {}).get("size", ""))
            if maximum.isdigit() and len(mime["bytes"]) > int(maximum):
                return {"status": "rejected", "notice": "Message exceeds the mail server size limit. Remove an attachment."}
            options = [f"size={len(mime['bytes'])}"] if maximum else []
            code, _ = conn.mail(cfg.address, options=options)
            if code != 250:
                return {"status": "rejected", "error_category":"PROVIDER_4XX" if code<500 else "PROVIDER_5XX",
                        "retryable":400<=code<500,"notice": "Mail server rejected the sender. Nothing was sent."}
            # All recipients must be accepted before DATA; avoid partial-recipient sends/retries.
            refused = False
            temporary = True
            for recipient in mime["recipients"]:
                code, _ = conn.rcpt(recipient)
                refused = refused or code not in (250, 251)
                if code not in (250,251) and not 400<=code<500:temporary=False
            if refused:
                conn.rset()
                return {"status": "rejected", "retryable":temporary,
                        "error_category":"PROVIDER_4XX" if temporary else "PROVIDER_5XX",
                        "notice": "A recipient was rejected. Nothing was sent; check the addresses."}
            data_started = True
            report_progress(progress, 75, "Sending email…")
            # Submission can include provider spam/virus scanning after DATA. The
            # short connection timeout must not abandon a still-processing send.
            # This is a response deadline, not a retry of an ambiguous delivery.
            if getattr(conn, 'sock', None) is not None:
                conn.sock.settimeout(cfg.data_timeout)
            code, _ = conn.data(mime["bytes"])
            if code == 250:
                report_progress(progress, 100, "Sent")
                return {"status": "accepted", "notice": "Mail server accepted the email."}
            return {"status": "rejected", "retryable":400<=code<500,
                    "error_category":"PROVIDER_4XX" if code<500 else "PROVIDER_5XX",
                    "notice": "Mail server rejected the message. Nothing was accepted."}
        except smtplib.SMTPDataError as error:
            return {"status": "rejected", "retryable":400<=error.smtp_code<500,
                    "error_category":"PROVIDER_4XX" if 400<=error.smtp_code<500 else "PROVIDER_5XX", "notice": "Mail server rejected the message. Nothing was accepted."}
        except Exception as error:
            LOGGER.warning("Email SMTP operation failed (%s)", type(error).__name__)
            category='AUTH' if isinstance(error,smtplib.SMTPAuthenticationError) else 'TIMEOUT' if isinstance(error,TimeoutError) else 'NETWORK' if isinstance(error,(OSError,smtplib.SMTPServerDisconnected)) else 'UNKNOWN'
            if data_started:
                return {"status": "unknown", "error_category":category,"notice": "Confirming original send. Do not resend."}
            return {"status": "rejected", "retryable":category in {'TIMEOUT','NETWORK'},
                    "error_category":category,"notice": "Could not send email. Check SMTP connection settings."}
        finally:
            LOGGER.info('email_smtp_attempt message_id=%s duration_ms=%.1f data_started=%s',mime.get('message_id',''),(time.monotonic()-started)*1000,data_started)
            if conn is not None:
                try:
                    if getattr(conn, 'sock', None) is not None:
                        conn.sock.settimeout(cfg.timeout)
                    conn.quit()
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass


class SendRegistry:
    """Process-wide operation receipts, no body/attachment content. Claim before network I/O."""
    def __init__(self):
        self.lock, self.receipts, self.copies = Lock(), {}, {}

    def get(self, operation_id, mailbox):
        """Read-only recovery after an interrupted Streamlit run."""
        with self.lock:
            return dict(self.receipts.get((mailbox.casefold(), operation_id), {}))

    def confirm_present(self, operation_id, mailbox):
        """Positive Sent-folder Message-ID evidence, never inferred from absence."""
        with self.lock:
            row=self.receipts[(mailbox.casefold(),operation_id)]
            row.update(status='accepted',notice='Sent',sent_at=datetime.now(timezone.utc).isoformat())
            return dict(row)

    def submit(self, operation_id, mailbox, mime, provider, *, progress=None):
        operation_id = str(uuid.UUID(operation_id))
        key = (mailbox.casefold(), operation_id)
        fingerprint = hashlib.sha256(mime["bytes"]).hexdigest()
        with self.lock:
            if key in self.receipts:
                return dict(self.receipts[key])
            if len(self.receipts) >= 10_000:
                return {"status": "rejected", "notice": "Send receipt capacity reached. Contact the administrator."}
            self.receipts[key] = {"status": "in_progress", "notice": "Sending…", "message_id": mime["message_id"],
                                  "fingerprint": fingerprint, "operation_id": operation_id}
        # A rerun or simultaneous click sees the claim and cannot submit again.
        def update_progress(percent, label):
            if percent == 100:
                # SMTP DATA acceptance is known before QUIT or Sent-folder I/O.
                with self.lock:
                    self.receipts[key].update(status="accepted", notice="Sent",
                                             sent_at=datetime.now(timezone.utc).isoformat())
            report_progress(progress, percent, label)
        try:
            result = provider.submit(mime, mailbox=mailbox, progress=update_progress)
        except BaseException:
            # Interruption cannot prove that SMTP did not accept DATA.
            with self.lock:
                if self.receipts[key]["status"] != "accepted":
                    self.receipts[key].update(status="unknown", notice="Send interrupted. Check Sent before taking further action.")
            raise
        with self.lock:
            if self.receipts[key]["status"] != "accepted" or result.get("status") == "accepted":
                self.receipts[key].update(result)
            if self.receipts[key]["status"] == "accepted":
                self.receipts[key].setdefault("sent_at", datetime.now(timezone.utc).isoformat())
            return dict(self.receipts[key])

    def save_sent(self, operation_id, mailbox, imap, mime, folder, policy, *, retry=False):
        """Serialise copy attempts across reruns; never retain message content here."""
        key = (mailbox.casefold(), operation_id)
        with self.lock:
            result = self.receipts.get(key, {})
            if (result.get("status") != "accepted" or
                    result.get("fingerprint") != hashlib.sha256(mime["bytes"]).hexdigest()):
                return {"status": "unknown", "notice": "Sent copy requires a confirmed send receipt."}
            lock, receipt = self.copies.setdefault(key, (Lock(), {}))
        if not lock.acquire(blocking=False):
            return {"status": "pending", "notice": "Sent copy is being checked."}
        try:
            return reconcile_sent(imap, mime, folder, policy, receipt=receipt, retry=retry)
        finally:
            lock.release()


SEND_REGISTRY = SendRegistry()


def reconcile_sent(imap, mime, sent_folder, policy="verify", *, receipt=None, retry=False):
    receipt = receipt if receipt is not None else {}
    if not sent_folder:
        return {"status": "failed", "retryable": True, "notice": "Map the real Sent folder in Email settings, then retry saving the copy."}
    if receipt.get("saved"):
        return dict(receipt["saved"])
    try:
        found = imap.find_message_id(sent_folder, mime["message_id"])
        if found:
            receipt["saved"] = {"status": "present", "uid": found[-1], "notice": "Sent copy verified in the real mailbox."}
            return dict(receipt["saved"])
        if retry and receipt.get("retryable"):
            receipt.pop("append_attempted", None)
        if receipt.get("retryable") and not retry:
            return {"status": "failed", "retryable": True, "notice": "The Sent copy could not be saved. Retry saving the copy."}
        if policy == "append" and not receipt.get("append_attempted"):
            receipt["append_attempted"] = True  # An interrupted APPEND is never blindly retried.
            receipt["retryable"] = False
            try:
                imap.append_message(sent_folder, mime["bytes"])
            except MailboxError as error:
                if error.code in {"append_not_started", "append_rejected"}:
                    receipt["retryable"] = True
                    return {"status": "failed", "retryable": True, "notice": "The Sent copy could not be saved. Retry saving the copy."}
                raise
            receipt["saved"] = {"status": "appended", "notice": "Saved a Sent copy in the real mailbox."}
            return dict(receipt["saved"])
        if receipt.get("append_attempted"):
            return {"status": "unknown", "notice": "Sent-copy storage is uncertain. Check the copy without resending or appending again."}
        return {"status": "pending", "notice": "Sent copy is not visible yet. Check again without resending."}
    except Exception as error:
        LOGGER.warning("Email Sent copy unavailable (%s)", type(error).__name__)
        return {"status": "unknown", "retryable": not receipt.get("append_attempted", False),
                "notice": "Sent storage could not be verified. Do not resend."}
