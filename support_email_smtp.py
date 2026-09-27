"""Explicit SMTP submission and in-process send receipts. No automatic retries or import I/O."""
from dataclasses import dataclass, field
import hashlib
import logging
import os
import smtplib
import ssl
from threading import Lock
import uuid

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
                return {"status": "rejected", "notice": "Mail server rejected the sender. Nothing was sent."}
            # All recipients must be accepted before DATA; avoid partial-recipient sends/retries.
            refused = False
            for recipient in mime["recipients"]:
                code, _ = conn.rcpt(recipient)
                refused = refused or code not in (250, 251)
            if refused:
                conn.rset()
                return {"status": "rejected", "notice": "A recipient was rejected. Nothing was sent; check the addresses."}
            data_started = True
            report_progress(progress, 75, "Sending email…")
            code, _ = conn.data(mime["bytes"])
            if code == 250:
                report_progress(progress, 100, "Sent")
                return {"status": "accepted", "notice": "Mail server accepted the email."}
            return {"status": "rejected", "notice": "Mail server rejected the message. Nothing was accepted."}
        except smtplib.SMTPDataError:
            return {"status": "rejected", "notice": "Mail server rejected the message. Nothing was accepted."}
        except Exception as error:
            LOGGER.warning("Email SMTP operation failed (%s)", type(error).__name__)
            if data_started:
                return {"status": "unknown", "notice": "Delivery status is uncertain. Do not resend; check Sent and the recipient first."}
            return {"status": "rejected", "notice": "Could not send email. Check SMTP connection settings."}
        finally:
            if conn is not None:
                try:
                    conn.quit()
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass


class SendRegistry:
    """Process-wide operation receipts, no body/attachment content. Claim before network I/O."""
    def __init__(self):
        self.lock, self.receipts = Lock(), {}

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
                                  "fingerprint": fingerprint}
        # A rerun or simultaneous click sees the claim and cannot submit again.
        def update_progress(percent, label):
            if percent == 100:
                # SMTP DATA acceptance is known before QUIT or Sent-folder I/O.
                with self.lock:
                    self.receipts[key].update(status="accepted", notice="Sent")
            report_progress(progress, percent, label)
        try:
            result = provider.submit(mime, mailbox=mailbox, **({"progress": update_progress} if progress else {}))
        except BaseException:
            # Interruption cannot prove that SMTP did not accept DATA.
            with self.lock:
                if self.receipts[key]["status"] != "accepted":
                    self.receipts[key].update(status="unknown", notice="Send interrupted. Check Sent before taking further action.")
            raise
        with self.lock:
            self.receipts[key].update(result)
            return dict(self.receipts[key])


SEND_REGISTRY = SendRegistry()


def reconcile_sent(imap, mime, sent_folder, policy="verify", *, receipt=None):
    receipt = receipt if receipt is not None else {}
    if not sent_folder:
        return {"status": "pending", "notice": "Map the real Sent folder to verify its copy."}
    try:
        if imap.find_message_id(sent_folder, mime["message_id"]):
            return {"status": "present", "notice": "Sent copy verified in the real mailbox."}
        if policy == "append" and not receipt.get("append_attempted"):
            # Enable only after a supervised test confirms the server does not save Sent itself.
            receipt["append_attempted"] = True  # An interrupted APPEND is never blindly retried.
            imap.append_message(sent_folder, mime["bytes"])
            return {"status": "appended", "notice": "Saved a Sent copy in the real mailbox."}
        return {"status": "pending", "notice": "Sent copy is not visible yet. Check again without resending."}
    except MailboxError:
        return {"status": "unknown", "notice": "Sent storage could not be verified. Do not resend."}
