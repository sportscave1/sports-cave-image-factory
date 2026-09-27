"""Live, read-only mailbox adapter. No database, SMTP, disk cache or import-time I/O."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser, BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
import hashlib
import imaplib
import logging
import os
import re
import ssl
import time
from typing import Protocol


LOGGER = logging.getLogger(__name__)
SAFE_ERROR = "Email connection failed. Check Render email credentials."
MAX_TEXT_BYTES = 512 * 1024
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
HEADER_FIELDS = "FROM TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES CONTENT-TYPE"


class MailboxError(RuntimeError):
    """Only constant, safe messages may cross the provider boundary."""


@dataclass(frozen=True)
class Configuration:
    host: str = "ventraip.email"
    port: int = 993
    address: str = "hello@sportscaveshop.com"
    password: str = field(default="", repr=False)
    use_ssl: bool = True
    timeout: float = 8

    @property
    def configured(self):
        return bool(self.password and self.host and self.port == 993 and self.use_ssl
                    and re.fullmatch(r"[^\s@<>]+@[^\s@<>]+", self.address))

    @property
    def scope(self):
        # A credential rotation cannot reuse a prior authenticated session cache.
        return (self.host, self.port, self.address.casefold(), self.use_ssl,
                hashlib.sha256(self.password.encode()).hexdigest())


def load_configuration(environ=None):
    env = os.environ if environ is None else environ
    try:
        port = int(env.get("SPORTSCAVE_EMAIL_IMAP_PORT", "993"))
    except (ValueError, TypeError):
        port = 0
    return Configuration(
        host=env.get("SPORTSCAVE_EMAIL_IMAP_HOST", "ventraip.email").strip(),
        port=port,
        address=env.get("SPORTSCAVE_EMAIL_ADDRESS", "hello@sportscaveshop.com").strip(),
        password=env.get("SPORTSCAVE_EMAIL_PASSWORD", ""),
        use_ssl=env.get("SPORTSCAVE_EMAIL_IMAP_SSL", "true").casefold() == "true",
    )


def decoded(value):
    try:
        return str(make_header(decode_header(str(value or ""))))
    except (LookupError, UnicodeError, ValueError):
        return str(value or "")


def addresses(values):
    result = []
    values = [str(v) for v in values]
    try:
        parsed = getaddresses(values, strict=False)
    except TypeError:  # Python 3.12 deployments before the strict parsing backport.
        parsed = getaddresses(values)
    for name, address in parsed:
        if address:
            result.append({"name": decoded(name), "email": address.strip().casefold()})
    return result


def message_ids(value):
    return tuple(dict.fromkeys(re.findall(r"<[^<>\s]+>", str(value or ""))))


def parse_date(value):
    try:
        dt = parsedate_to_datetime(str(value))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (TypeError, ValueError, OverflowError):
        return None


def parse_headers(raw, *, uid, uidvalidity, flags=(), internaldate="", folder="INBOX"):
    base = {"uid": str(uid), "uidvalidity": str(uidvalidity), "folder": folder,
            "flags": tuple(flags), "unread": "\\Seen" not in flags,
            "subject": "(Unparseable message)", "sender": {"name": "", "email": ""},
            "to": [], "cc": [], "message_id": "", "references": (), "in_reply_to": (),
            "date": None, "received_at": parse_date(internaldate), "error": ""}
    try:
        msg = BytesHeaderParser(policy=policy.default).parsebytes(raw)
        base.update(subject=decoded(msg.get("Subject", "(No subject)")),
                    sender=(addresses(msg.get_all("From", [])) or [base["sender"]])[0],
                    to=addresses(msg.get_all("To", [])), cc=addresses(msg.get_all("Cc", [])),
                    message_id=next(iter(message_ids(msg.get("Message-ID"))), ""),
                    references=message_ids(" ".join(msg.get_all("References", []))),
                    in_reply_to=message_ids(" ".join(msg.get_all("In-Reply-To", []))),
                    date=parse_date(msg.get("Date")))
        base["received_at"] = base["received_at"] or base["date"]
        if msg.defects:
            base["error"] = "Some message headers could not be read."
    except Exception:
        base["error"] = "This message's headers could not be read."
    return base


class _ReadableHTML(HTMLParser):
    """HTML becomes inert text; never emit original tags, URLs or attributes."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head", "iframe", "object", "svg", "template"}:
            self.hidden.append(tag)
        if not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "blockquote"}:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]
        elif not self.hidden and tag in {"p", "div", "li", "tr", "blockquote"}:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def html_to_text(value):
    parser = _ReadableHTML()
    parser.feed(value)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", "".join(parser.chunks)).strip()


def _imap_tree(data):
    """Parse a bounded IMAP parenthesized value, including quoted/literal strings."""
    pos = 0

    def value(depth=0):
        nonlocal pos
        if depth > 30:
            raise ValueError("MIME nesting limit")
        while pos < len(data) and data[pos:pos+1].isspace():
            pos += 1
        if pos >= len(data):
            raise ValueError("Incomplete MIME structure")
        if data[pos] == 40:
            pos += 1
            values = []
            while True:
                while pos < len(data) and data[pos:pos+1].isspace():
                    pos += 1
                if pos >= len(data):
                    raise ValueError("Incomplete MIME structure")
                if data[pos] == 41:
                    pos += 1
                    return values
                values.append(value(depth + 1))
        if data[pos] == 34:
            pos += 1
            result = bytearray()
            while pos < len(data):
                char = data[pos]
                pos += 1
                if char == 34:
                    return result.decode("utf-8", "replace")
                if char == 92 and pos < len(data):
                    char = data[pos]
                    pos += 1
                result.append(char)
            raise ValueError("Incomplete quoted string")
        literal = re.match(rb"\{(\d+)\}\r\n", data[pos:])
        if literal:
            size = int(literal[1])
            pos += literal.end()
            result = data[pos:pos+size]
            if len(result) != size:
                raise ValueError("Incomplete literal")
            pos += size
            return result.decode("utf-8", "replace")
        end = pos
        while end < len(data) and data[end] not in b" ()\r\n":
            end += 1
        token = data[pos:end].decode("ascii", "replace")
        if end == pos:
            raise ValueError("Invalid token")
        pos = end
        return None if token.upper() == "NIL" else token

    return value()


def _params(value):
    if not isinstance(value, list):
        return {}
    return {str(value[i]).casefold(): str(value[i+1] or "") for i in range(0, len(value)-1, 2)}


def _filename(params):
    # Let the stdlib decode RFC 2231 continuations and RFC 2047 filenames.
    from email.message import Message
    msg = Message()
    msg.add_header("Content-Disposition", "attachment", **params)
    return decoded(msg.get_filename() or "")


def mime_parts(tree, prefix="", inherited_attachment=False, alternative_group=""):
    if not isinstance(tree, list) or len(tree) < 2:
        raise ValueError("Invalid MIME structure")
    if isinstance(tree[0], list):
        count = next((i for i, v in enumerate(tree) if not isinstance(v, list)), len(tree))
        disposition = tree[count+2] if len(tree) > count+2 else None
        attached = inherited_attachment or (isinstance(disposition, list)
                    and str(disposition[0]).casefold() == "attachment")
        group = (prefix or "root") if str(tree[count]).casefold() == "alternative" else alternative_group
        result = []
        for i, child in enumerate(tree[:count], 1):
            result.extend(mime_parts(child, f"{prefix}.{i}" if prefix else str(i), attached, group))
        return result
    if len(tree) < 7:
        raise ValueError("Incomplete MIME part")
    content_type = f"{tree[0]}/{tree[1]}".casefold()
    extension_start = 8 if str(tree[0]).casefold() == "text" else 10 if content_type == "message/rfc822" else 7
    disposition = tree[extension_start+1] if len(tree) > extension_start+1 else None
    params = _params(tree[2])
    dparams = _params(disposition[1]) if isinstance(disposition, list) and len(disposition) > 1 else {}
    filename = _filename(dparams) or decoded(params.get("name", ""))
    attachment = bool(inherited_attachment or filename or content_type not in {"text/plain", "text/html"}
                      or (isinstance(disposition, list) and str(disposition[0]).casefold() == "attachment"))
    return [{"section": prefix or "1", "content_type": content_type,
             "charset": params.get("charset", "utf-8"), "encoding": str(tree[5] or "7bit"),
             "encoded_size": int(tree[6]), "filename": filename or (f"attachment-{prefix or '1'}" if attachment else ""),
             "attachment": attachment, "alternative_group": alternative_group}]


def decode_part(raw, part):
    # Synthetic MIME headers contain only validated MIME tokens, not arbitrary sender input.
    encoding = part["encoding"].casefold()
    if encoding not in {"base64", "quoted-printable", "7bit", "8bit", "binary"}:
        encoding = "8bit"
    msg = BytesParser(policy=policy.default).parsebytes(
        f"Content-Transfer-Encoding: {encoding}\r\n\r\n".encode() + raw)
    return msg.get_payload(decode=True) or b""


class EmailProvider(Protocol):
    def test_connection(self): ...
    def list_headers(self, limit=50, folder="INBOX"): ...
    def read_message(self, header): ...
    def read_attachment(self, header, section): ...


class ImapProvider:
    def __init__(self, configuration, *, connection_factory=None):
        self.configuration = configuration
        self.connection_factory = connection_factory or imaplib.IMAP4_SSL

    @contextmanager
    def _connection(self, folder="INBOX", expected_validity=None):
        conn = None
        try:
            cfg = self.configuration
            if not cfg.configured:
                raise MailboxError("Email is not configured. Add the secure IMAP environment variables.")
            # Folder paths come from LIST in a future version. V1 deliberately exposes INBOX only.
            if folder != "INBOX":
                raise MailboxError("Only INBOX is available in Email V1.")
            conn = self.connection_factory(cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=cfg.timeout)
            conn.debug = 0
            self._ok(conn.login(cfg.address, cfg.password))
            count = int(self._ok(conn.select(folder, readonly=True))[0])
            _, validity = conn.response("UIDVALIDITY")
            uidvalidity = validity[0].decode("ascii")
            if not uidvalidity.isdigit():
                raise MailboxError(SAFE_ERROR)
            if expected_validity is not None and uidvalidity != str(expected_validity):
                raise MailboxError("Mailbox identifiers changed. Refresh Inbox before opening this message.")
            yield conn, count, uidvalidity
        except MailboxError:
            raise
        except Exception as error:
            # Never log provider response text, arguments, repr, tracebacks or credentials.
            LOGGER.warning("Support email IMAP operation failed (%s)", type(error).__name__)
            raise MailboxError(SAFE_ERROR) from None
        finally:
            if conn is not None:
                try:
                    conn.logout()  # Never CLOSE/EXPUNGE, even during failure cleanup.
                except Exception:
                    try:
                        conn.shutdown()
                    except Exception:
                        pass

    @staticmethod
    def _ok(response):
        status, data = response
        if status != "OK":
            raise MailboxError(SAFE_ERROR)
        return data

    def test_connection(self):
        with self._connection() as (conn, count, validity):
            folders = self._ok(conn.list())
            # Discovery results are informational only; never infer or select a Sent folder.
            return {"count": count, "folders": tuple(v.decode("utf-8", "replace") for v in folders if isinstance(v, bytes)),
                    "uidvalidity": validity}

    def list_headers(self, limit=50, folder="INBOX"):
        limit = min(max(int(limit), 1), 1000)
        with self._connection(folder) as (conn, count, validity):
            rows = []
            if count:
                # Sequence numbers are used only for this bounded snapshot; details always use UID.
                response = self._ok(conn.fetch(f"{max(1, count-limit+1)}:{count}",
                    f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"))
                for item in response:
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    envelope, raw = item
                    uid = re.search(rb"\bUID (\d+)", envelope)
                    if not uid:
                        continue
                    internal = re.search(rb'INTERNALDATE "([^"]+)"', envelope)
                    rows.append(parse_headers(raw, uid=uid[1].decode(), uidvalidity=validity,
                        flags=tuple(v.decode("ascii", "replace") for v in imaplib.ParseFlags(envelope)),
                        internaldate=internal[1].decode() if internal else "", folder=folder))
            return {"messages": rows, "total": count, "uidvalidity": validity,
                    "refreshed_at": datetime.now(timezone.utc), "has_more": count > limit}

    def _structure(self, conn, uid):
        if not re.fullmatch(r"[1-9]\d*", str(uid)):
            raise MailboxError("Invalid message identifier. Refresh Inbox.")
        data = self._ok(conn.uid("FETCH", str(uid), "(UID BODYSTRUCTURE)"))
        chunks = []
        for item in data:
            if isinstance(item, tuple):
                chunks.extend([item[0], b"\r\n", item[1]])
            elif isinstance(item, bytes):
                chunks.append(item)
        raw = b"".join(chunks)
        match = re.search(rb"BODYSTRUCTURE\s+", raw, re.I)
        if not match:
            raise MailboxError("This message is no longer available. Refresh Inbox.")
        return mime_parts(_imap_tree(raw[match.end():]))

    def _part(self, conn, uid, part, maximum):
        if not re.fullmatch(r"\d+(?:\.\d+)*", part["section"]):
            raise MailboxError("This MIME part cannot be opened.")
        if not 0 <= part["encoded_size"] <= maximum:
            raise MailboxError("This part is too large for Email V1. Open it in your existing mail client.")
        data = self._ok(conn.uid("FETCH", str(uid), f"(UID BODY.PEEK[{part['section']}]<0.{maximum+1}>)"))
        payloads = [item[1] for item in data if isinstance(item, tuple)]
        if len(payloads) != 1 or len(payloads[0]) > maximum:
            raise MailboxError("This message part could not be read safely.")
        return decode_part(payloads[0], part)

    def read_message(self, header):
        with self._connection(header["folder"], header["uidvalidity"]) as (conn, _, __):
            parts = self._structure(conn, header["uid"])
            if len(parts) > 100:
                raise MailboxError("This message has too many MIME parts. Open it in your existing mail client.")
            text_parts = [p for p in parts if not p["attachment"]]
            # Prefer plain text within each multipart/alternative; retain distinct mixed text parts.
            plain_parents = {p["alternative_group"] for p in text_parts
                             if p["content_type"] == "text/plain" and p["alternative_group"]}
            chosen = [p for p in text_parts if p["content_type"] == "text/plain" or
                      p["alternative_group"] not in plain_parents]
            result, warnings = [], []
            deadline = time.monotonic() + 20
            for part in chosen[:12]:
                if time.monotonic() > deadline:
                    warnings.append("Message read time limit reached. Open remaining content in your mail client.")
                    break
                if part["encoded_size"] > MAX_TEXT_BYTES:
                    warnings.append("A large text part was omitted. Open it in your existing mail client.")
                    continue
                raw = self._part(conn, header["uid"], part, MAX_TEXT_BYTES)
                try:
                    text = raw.decode(part["charset"], "replace")
                except LookupError:
                    text = raw.decode("utf-8", "replace")
                result.append(html_to_text(text) if part["content_type"] == "text/html" else text)
            if len(chosen) > 12:
                warnings.append("Additional text parts are available in your existing mail client.")
            return {"text": "\n\n".join(result), "attachments": [p for p in parts if p["attachment"]],
                    "warnings": warnings}

    def read_attachment(self, header, section):
        with self._connection(header["folder"], header["uidvalidity"]) as (conn, _, __):
            # Re-read authoritative structure instead of trusting a stale UI filename/part size.
            part = next((p for p in self._structure(conn, header["uid"])
                         if p["section"] == section and p["attachment"]), None)
            if part is None:
                raise MailboxError("This attachment is no longer available. Refresh Inbox.")
            return {"data": self._part(conn, header["uid"], part, MAX_ATTACHMENT_BYTES),
                    "filename": re.sub(r'[\\/\x00-\x1f]', "_", part["filename"])[:200] or "attachment"}
