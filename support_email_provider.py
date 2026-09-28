"""Live IMAP adapter. Reads are non-mutating; writes require explicit method calls."""
from contextlib import contextmanager, nullcontext, ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser, BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from functools import wraps
import hashlib
import base64
import imaplib
import logging
import os
import re
import socket
import ssl
import time
import errno
from typing import Protocol
from urllib.parse import urlsplit
from support_email_runtime import RUNTIME, Deferred, operation


LOGGER = logging.getLogger(__name__)
SAFE_ERROR = "Email server temporarily unavailable. Retry connection."
MAX_TEXT_BYTES = 512 * 1024
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
HEADER_FIELDS = "FROM REPLY-TO TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES CONTENT-TYPE"


class MailboxError(RuntimeError):
    """Only constant, safe messages may cross the provider boundary."""

    def __init__(self, message, *, code="operation", retryable=False, stage="operation"):
        super().__init__(message)
        self.code, self.retryable = code, retryable
        self.stage = stage


FAILURES = {
    "configuration": "Mailbox is not configured.",
    "authentication": "Mailbox authentication failed. Check server credentials.",
    "timeout": "Email connection timed out. Retry connection.",
    "tls": "Secure email connection failed. TLS verification was unsuccessful.",
    "dns": "Email server address could not be resolved. Retry connection.",
    "folders": "Folder listing failed. Retry connection.",
    "select": "Mailbox folder could not be opened. Retry connection.",
    "temporary": SAFE_ERROR,
    "operation": SAFE_ERROR,
    "status": "Mailbox status check failed. Retrying automatically.",
    "refused": SAFE_ERROR, "network": SAFE_ERROR, "reset": SAFE_ERROR,
    "bye": SAFE_ERROR, "limit": SAFE_ERROR, "protocol": SAFE_ERROR,
    "deferred": "Connection interrupted. Reconnecting automatically.",
    "busy": "Mailbox is busy. Try again shortly.",
}


def _failure(error, stage):
    stage = getattr(error, "email_stage", stage)
    if isinstance(error, Deferred):
        code = "deferred"
    elif isinstance(error, TimeoutError):
        code = "timeout"
    elif isinstance(error, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
        code = "reset"
    elif isinstance(error, ssl.SSLError):
        code = "tls"
    elif isinstance(error, socket.gaierror):
        code = "dns"
    elif isinstance(error, imaplib.IMAP4.error) and re.search(r"too many|connection limit|rate.?limit|maximum.*connections", str(error), re.I):
        code = "limit"
    elif isinstance(error, imaplib.IMAP4.abort):
        code = "bye"
    elif isinstance(error, ConnectionRefusedError):
        code = "refused"
    elif isinstance(error, (ConnectionResetError, BrokenPipeError, EOFError)):
        code = "reset"
    elif isinstance(error, OSError) and error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH}:
        code = "network"
    elif isinstance(error, OSError):
        code = "temporary"
    elif isinstance(error, imaplib.IMAP4.error) and stage == "authentication":
        code = "authentication"
    elif stage in {"folders", "select", "status"}:
        code = stage
    else:
        code = "protocol"
    return MailboxError(FAILURES[code], code=code, stage=stage,
                        retryable=code in {"timeout", "dns", "temporary", "refused", "network", "reset", "bye"})


def _retry_read(method):
    """Replay only explicitly safe reads, on a fresh socket, at most once."""
    @wraps(method)
    def read(self, *args, **kwargs):
        for attempt in range(2):
            try:
                with operation(force=True) if attempt else nullcontext():
                    return method(self, *args, **kwargs)
            except MailboxError as error:
                if attempt or not error.retryable:
                    raise
                LOGGER.info("email_imap_retry code=%s", error.code)
    return read


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
            "to": [], "cc": [], "reply_to": [], "message_id": "", "references": (), "in_reply_to": (),
            "date": None, "received_at": parse_date(internaldate), "error": ""}
    try:
        msg = BytesHeaderParser(policy=policy.default).parsebytes(raw)
        base.update(subject=decoded(msg.get("Subject", "(No subject)")),
                    sender=(addresses(msg.get_all("From", [])) or [base["sender"]])[0],
                    to=addresses(msg.get_all("To", [])), cc=addresses(msg.get_all("Cc", [])),
                    reply_to=addresses(msg.get_all("Reply-To", [])),
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
    """HTML becomes inert text. Only safe anchor destinations survive as visible text."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.chunks = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head", "iframe", "object", "svg", "template"}:
            self.hidden.append(tag)
        if not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "blockquote"}:
            self.chunks.append("\n")
        if not self.hidden and tag == "a":
            url = str(dict(attrs).get("href") or "").strip()
            try:
                parsed = urlsplit(url)
                allowed = parsed.scheme.lower() in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
                allowed = allowed and not any(ord(c) < 32 or c in '<>"\\' for c in url)
            except ValueError:
                allowed = False
            self.links.append(url if allowed else "")

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]
        elif not self.hidden and tag in {"p", "div", "li", "tr", "blockquote"}:
            self.chunks.append("\n")
        elif not self.hidden and tag == "a" and self.links:
            url = self.links.pop()
            if url:
                self.chunks.append(f" ({url}) ")

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
    def list_headers(self, limit=50, folder="INBOX", *, query="", field="TEXT", since=None, before=None, previews=False): ...
    def read_message(self, header): ...
    def read_attachment(self, header, section): ...
    def discover_folders(self): ...
    def set_flag(self, header, flag, enabled): ...
    def move_message(self, header, destination): ...
    def delete_trash_messages(self, headers, *, trash_folder, folder_mapping=None): ...
    def related_headers(self, folder, identifiers, limit=100): ...
    def related_headers_many(self, folders, identifiers, limit=100): ...
    def find_message_id(self, folder, message_id): ...
    def append_message(self, folder, mime_bytes, *, draft=False): ...
    def read_draft(self, header): ...


FOLDER_ROLES = {"\\sent": "sent", "\\drafts": "drafts", "\\archive": "archive",
                "\\junk": "junk", "\\trash": "trash"}


def folder_argument(name):
    if not isinstance(name, str) or not name or len(name) > 512 or any(ord(c) < 32 for c in name):
        raise MailboxError("Invalid mailbox folder.")
    # Preserve the exact LIST wire name, including modified UTF-7; never interpolate IMAP syntax.
    if name.upper() == "INBOX":
        return "INBOX"
    return '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'


def folder_label(wire_name):
    def replace(match):
        if not match[1]:
            return "&"
        try:
            token = match[1].replace(",", "/")
            return base64.b64decode(token + "=" * (-len(token) % 4)).decode("utf-16-be")
        except (ValueError, UnicodeError):
            return match[0]
    return re.sub(r"&([^-]*)-", replace, wire_name)


def parse_folders(data):
    result = []
    for row in data:
        try:
            raw = row[0] + b"\r\n" + row[1] if isinstance(row, tuple) else row
            flags, delimiter, name = _imap_tree(b"(" + raw + b")")
            if not isinstance(name, str) or "\\noselect" in [str(f).casefold() for f in flags]:
                continue
            folder_argument(name)
            role = "inbox" if name.upper() == "INBOX" else next(
                (FOLDER_ROLES[str(f).casefold()] for f in flags if str(f).casefold() in FOLDER_ROLES), "")
            result.append({"name": name, "label": folder_label(name), "role": role,
                           "delimiter": delimiter, "flags": flags, "unread": None})
        except (ValueError, TypeError, MailboxError):
            continue
    return result


def folder_roles(folders, overrides=None):
    """Observed LIST names only: explicit mapping, SPECIAL-USE, then an unambiguous Sent fallback."""
    names = {f["name"] for f in folders}
    roles = {}
    for role in ("inbox", "sent", "drafts", "archive", "junk", "trash"):
        matches = [f["name"] for f in folders if f["role"] == role]
        if len(matches) == 1:
            roles[role] = matches[0]
        if role == "sent" and not matches:
            fallbacks = [f["name"] for f in folders if not f["role"] and
                         f["name"].casefold() in {"sent", "sent items", "sent messages", "inbox.sent"}]
            if len(fallbacks) == 1:
                roles[role] = fallbacks[0]
        if (overrides or {}).get(role) in names:
            roles[role] = overrides[role]
    # An explicit mapping must not accidentally turn a discovered Sent folder into Trash too.
    collisions = {name for name in roles.values() if list(roles.values()).count(name) > 1}
    roles = {role: name for role, name in roles.items() if name not in collisions}
    return roles


def _quoted_search(value):
    value = str(value)
    if len(value) > 512 or any(ord(c) < 32 for c in value):
        raise MailboxError("Search is too long or contains unsupported characters.")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def search_criteria(query, field="TEXT", since=None, before=None):
    if field not in {"TEXT", "SUBJECT", "FROM", "TO"}:
        raise MailboxError("Unsupported mailbox search field.")
    criteria = f"{field} {_quoted_search(query)}" if query else "ALL"
    for key, date in (("SINCE", since), ("BEFORE", before)):
        if date:
            try:
                value = datetime.strptime(str(date), "%Y-%m-%d").strftime("%d-%b-%Y")
            except ValueError:
                raise MailboxError("Use a valid search date.") from None
            criteria += f" {key} {value}"
    return criteria


_SSL_CLASS = imaplib.IMAP4_SSL


def _close_resources(connection):
    for attr in ("_file", "file", "sock"):
        resource = vars(connection).get(attr)
        if resource is not None:
            try:
                resource.close()
            except Exception:
                pass


class _ManagedSSL(_SSL_CLASS):
    """Also release partially constructed sockets on TLS/greeting failure."""
    def _create_socket(self, timeout):
        from support_email_transport import connect_tls
        return connect_tls(self.host, self.port, timeout, self.ssl_context)

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except BaseException:
            _close_resources(self)
            raise


class ImapProvider:
    def __init__(self, configuration, *, connection_factory=None, runtime=None, background=False):
        self.configuration = configuration
        self.connection_factory = connection_factory or (_ManagedSSL if imaplib.IMAP4_SSL is _SSL_CLASS else imaplib.IMAP4_SSL)
        # Injected transports are isolated by default; load tests explicitly share a runtime.
        self.runtime = runtime if runtime is not None else (RUNTIME if connection_factory is None else None)
        self.background = background

    @contextmanager
    def interactive_refresh(self):
        if self.runtime:
            self.runtime.invalidate(self.configuration.scope)
        with operation(force=True):
            yield

    @contextmanager
    def _connection(self, folder="INBOX", expected_validity=None, *, write=False):
        cfg = self.configuration
        gate = self.runtime.connection(cfg.scope, timeout=cfg.timeout, background=self.background) if self.runtime else nullcontext()
        try:
            with gate:
                with self._wire_connection(folder, expected_validity, write=write) as connection:
                    yield connection
        except Deferred as error:
            LOGGER.info("email_imap_deferred stage=acquire code=%s", error.reason)
            code = "deferred" if error.reason == "backoff" else "busy"
            raise MailboxError(FAILURES[code], code=code) from None
        finally:
            if write and self.runtime:
                # Invalidates snapshots, including in-flight poll results; never sockets.
                self.runtime.invalidate(cfg.scope)

    @contextmanager
    def _wire_connection(self, folder="INBOX", expected_validity=None, *, write=False):
        conn = None
        stage = "configuration"
        started = time.monotonic()
        try:
            cfg = self.configuration
            if not cfg.configured:
                raise MailboxError(FAILURES[stage], code=stage)
            argument = folder_argument(folder) if folder is not None else None
            stage = "connect"
            LOGGER.debug("email_imap_check_started")
            conn = self.connection_factory(cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=cfg.timeout)
            conn.debug = 0
            stage = "authentication"
            self._ok(conn.login(cfg.address, cfg.password), stage=stage)
            count, uidvalidity = 0, ""
            if argument is not None:
                stage = "select"
                count = int(self._ok(conn.select(argument, readonly=not write), stage=stage)[0])
                _, validity = conn.response("UIDVALIDITY")
                uidvalidity = validity[0].decode("ascii")
                if not uidvalidity.isdigit():
                    raise MailboxError(SAFE_ERROR)
            if expected_validity is not None and uidvalidity != str(expected_validity):
                raise MailboxError("Mailbox identifiers changed. Refresh Inbox before opening this message.")
            stage = "operation"
            yield conn, count, uidvalidity
            LOGGER.debug("email_imap_check_success duration_ms=%d", (time.monotonic() - started) * 1000)
        except MailboxError:
            raise
        except Exception as error:
            # Never log provider response text, arguments, repr, tracebacks or credentials.
            failure = _failure(error, stage)
            LOGGER.warning("email_imap_check_failure stage=%s code=%s type=%s errno=%s winerror=%s duration_ms=%d",
                failure.stage, failure.code, type(error).__name__,
                getattr(error, "errno", None) if isinstance(getattr(error, "errno", None), int) else None,
                getattr(error, "winerror", None) if isinstance(getattr(error, "winerror", None), int) else None,
                (time.monotonic() - started) * 1000)
            raise failure from None
        finally:
            if conn is not None:
                try:
                    conn.logout()  # Never CLOSE/EXPUNGE, even after a write.
                except Exception:
                    pass
                finally:
                    # logout can time out or be interrupted. shutdown only closes the
                    # transport; unlike IMAP CLOSE it never expunges mailbox messages.
                    try:
                        conn.shutdown()
                    except Exception:
                        pass
                    finally:
                        _close_resources(conn)

    @staticmethod
    def _ok(response, *, stage="operation"):
        status, data = response
        if status != "OK":
            # Classify known server responses but never print their text.
            limited = bool(re.search(r"too many|connection limit|rate.?limit|maximum.*connections", str(data), re.I))
            code = "limit" if limited else "bye" if status == "BYE" else stage
            LOGGER.warning("email_imap_check_failure stage=%s code=%s", stage, code)
            raise MailboxError(FAILURES[code], code=code, stage=stage, retryable=code == "folders")
        return data

    def _list_folders(self, conn):
        try:
            return self._ok(conn.list(), stage="folders")
        except MailboxError:
            raise
        except Exception as error:
            failure = _failure(error, "folders")
            LOGGER.warning("Support email IMAP failed (stage=folders code=%s type=%s)", failure.code, type(error).__name__)
            raise failure from None

    @_retry_read
    def test_connection(self):
        with self._connection() as (conn, count, validity):
            folders = self._list_folders(conn)
            # Discovery results are informational only; never infer or select a Sent folder.
            return {"count": count, "folders": tuple(v.decode("utf-8", "replace") for v in folders if isinstance(v, bytes)),
                    "uidvalidity": validity}

    def _inbox_status(self, conn):
        return self._folder_status("INBOX", lambda: conn)

    def _folder_status(self, folder, connection):
        scope = self.configuration.scope
        key = ("status", folder)
        cached = self.runtime.get(scope, key) if self.runtime else None
        if cached is not None:
            return cached
        generation = self.runtime.generation(scope) if self.runtime else 0
        try:
            raw = self._ok(connection().status(folder_argument(folder), "(UNSEEN MESSAGES UIDNEXT UIDVALIDITY)"), stage="status")
        except MailboxError:
            raise
        except Exception as error:
            failure = _failure(error, "status")
            LOGGER.warning("email_imap_check_failure stage=status code=%s type=%s", failure.code, type(error).__name__)
            raise failure from None
        values = dict(re.findall(rb"\b(UNSEEN|MESSAGES|UIDNEXT|UIDVALIDITY) (\d+)",
                                b" ".join(v for v in raw if isinstance(v, bytes))))
        if len(values) != 4 or int(values[b"UIDNEXT"]) < 1 or int(values[b"UIDVALIDITY"]) < 1:
            raise MailboxError(SAFE_ERROR)
        status = {key.decode().lower(): int(value) for key, value in values.items()}
        if self.runtime:
            self.runtime.put(scope, key, status, generation)
        return status

    def get_unread_count(self):
        """Dedicated lightweight count; no SELECT, headers, MIME or attachments."""
        with ExitStack() as stack:
            return self._folder_status("INBOX", lambda: stack.enter_context(self._connection(None))[0])["unseen"]

    def notification_snapshot(self, cursor=None):
        """One bounded operation: STATUS, then at most 50 new header-only UIDs.

        BODY.PEEK[HEADER.FIELDS] is IMAP's header fetch syntax; no message body
        section, preview, structure or attachment is requested here.
        """
        with ExitStack() as stack:
            conn = None
            def connection():
                nonlocal conn
                if conn is None:
                    conn = stack.enter_context(self._connection(None))[0]
                return conn
            status = self._folder_status("INBOX", connection)
            validity = str(status["uidvalidity"])
            previous = cursor or {}
            high = status["uidnext"] - 1
            rows = []
            if str(previous.get("uidvalidity")) == validity:
                low = int(previous.get("last_uid", 0)) + 1
                if low <= high:
                    conn = connection()
                    high = min(high, low + 49)
                    self._ok(conn.select('"INBOX"', readonly=True))
                    _, selected = conn.response("UIDVALIDITY")
                    if not selected or selected[0].decode("ascii") != validity:
                        raise MailboxError(SAFE_ERROR)
                    data = self._ok(conn.uid("FETCH", f"{low}:{high}",
                        "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"))
                    rows = [row for row in self._headers(data, validity, "INBOX")
                            if low <= int(row["uid"]) <= high]
                else:
                    high = max(high, int(previous.get("last_uid", 0)))
            return {**status, "uidvalidity": validity, "last_uid": high, "messages": rows}

    def notification_target(self, uidvalidity, uid, message_id=""):
        """Resolve one Inbox deep link on the Email page only, without changing flags."""
        if not str(uid).isdigit() or not str(uidvalidity).isdigit():
            return None
        with self._connection("INBOX") as (conn, _, validity):
            rows = self._fetch_uids(conn, [str(uid)], validity, "INBOX") if validity == str(uidvalidity) else []
            exact = next((r for r in rows if r["uid"] == str(uid) and
                          (not message_id or r["message_id"] == message_id)), None)
            if exact:
                return exact
            identifiers = message_ids(message_id)
            if len(identifiers) == 1 and identifiers[0] == message_id and len(message_id) <= 998:
                uids = self._search(conn, f"HEADER Message-ID {_quoted_search(message_id)}")
                if len(uids) > 50:
                    return None
                rows = self._fetch_uids(conn, uids, validity, "INBOX")
                exact = [r for r in rows if r["message_id"] == message_id]
                return exact[0] if len(exact) == 1 else None
        return None

    @_retry_read
    def discover_folders(self):
        with self._connection(None) as (conn, _, __):
            folders = parse_folders(self._list_folders(conn))
            deadline = time.monotonic() + 6
            for folder in [f for f in folders if f["role"]][:6]:
                if time.monotonic() > deadline:
                    break
                try:
                    response = self._ok(conn.status(folder_argument(folder["name"]), "(UNSEEN)"))
                    match = re.search(rb"UNSEEN (\d+)", b" ".join(v for v in response if isinstance(v, bytes)))
                    if match:
                        folder["unread"] = int(match[1])
                except Exception:
                    pass  # Counts are optional; never synthesize a zero count.
            return {"folders": folders, "capabilities": self._capabilities(conn)}

    @staticmethod
    def _capabilities(conn):
        return {c.decode("ascii").upper() if isinstance(c, bytes) else str(c).upper()
                for c in getattr(conn, "capabilities", ())}

    def _headers(self, data, validity, folder):
        rows = []
        for item in data:
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
        return rows

    def _search(self, conn, criteria):
        if criteria.isascii():
            response = conn.uid("SEARCH", None, criteria.encode("ascii"))
        else:
            response = conn.uid("SEARCH", "CHARSET", "UTF-8", criteria.encode("utf-8"))
        raw = self._ok(response)
        return [uid.decode() for part in raw if isinstance(part, bytes) for uid in part.split() if uid.isdigit()]

    def _fetch_uids(self, conn, uids, validity, folder):
        if not uids:
            return []
        return self._headers(self._ok(conn.uid("FETCH", ",".join(uids),
            f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])")), validity, folder)

    @_retry_read
    def list_headers(self, limit=50, folder="INBOX", *, query="", field="TEXT", since=None, before=None, previews=False):
        limit = min(max(int(limit), 1), 1000)
        with self._connection(folder) as (conn, count, validity):
            rows = []
            matched = count
            if query or since or before:
                uids = self._search(conn, search_criteria(query, field, since, before))
                matched = len(uids)
                rows = self._fetch_uids(conn, uids[-limit:], validity, folder)
            elif count:
                # Sequence numbers are used only for this bounded snapshot; details always use UID.
                response = self._ok(conn.fetch(f"{max(1, count-limit+1)}:{count}",
                    f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"))
                rows = self._headers(response, validity, folder)
            if previews and rows:
                self._previews(conn, rows)
            _, next_uid = conn.response("UIDNEXT")
            baseline = int(next_uid[0]) - 1 if next_uid and isinstance(next_uid[0], bytes) and next_uid[0].isdigit() else max((int(m["uid"]) for m in rows), default=0)
            return {"messages": rows, "total": count, "matched": matched, "uidvalidity": validity,
                    "live_uid": max(baseline, max((int(m["uid"]) for m in rows), default=0)),
                    "refreshed_at": datetime.now(timezone.utc), "has_more": matched > limit}

    def live_changes(self, folder, snapshot, *, limit=50, query="", field="TEXT"):
        # Different sessions share immutable deltas, never a connection or selection.
        key = ("live", folder, str(snapshot.get("uidvalidity")), snapshot.get("live_uid"), limit, query, field,
               tuple(sorted({str(m["uid"]) for m in [*snapshot.get("messages", [])[:1000],
                   *snapshot.get("visible_messages", [])[:100]] if m["folder"] == folder})))
        loader = lambda: self._live_changes(folder, snapshot, limit=limit, query=query, field=field)
        try:
            return self.runtime.check(self.configuration.scope, key, loader) if self.runtime else loader()
        except Deferred as error:
            code = "deferred" if error.reason == "backoff" else "busy"
            raise MailboxError(FAILURES[code], code=code) from None

    def _live_changes(self, folder, snapshot, *, limit=50, query="", field="TEXT"):
        """Bounded current-view sync: counters, loaded UID flags and new headers only."""
        limit = min(max(int(limit), 1), 1000)
        with self._connection(folder) as (conn, count, validity):
            status = self._folder_status(folder, lambda: conn)
            values = {key.upper().encode(): str(value).encode() for key, value in status.items()}
            if str(status["uidvalidity"]) != validity:
                raise MailboxError("Mailbox changed during the live check. Refresh to reconnect.")
            # Include a bounded opened thread/notification target outside the list page.
            known = list({m["uid"]: m for m in [*snapshot.get("messages", [])[:1000],
                *snapshot.get("visible_messages", [])[:100]] if m["folder"] == folder}.values())
            reset = str(snapshot.get("uidvalidity")) != validity
            flags, added = {}, []
            if reset:
                # A new UIDVALIDITY invalidates old identities, never their immutable body cache keys.
                if query:
                    uids = self._search(conn, search_criteria(query, field))[-limit:]
                    added = self._fetch_uids(conn, uids, validity, folder)
                elif count:
                    added = self._headers(self._ok(conn.fetch(f"{max(1, count-limit+1)}:{count}",
                        f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])")), validity, folder)
            else:
                if known:
                    data = self._ok(conn.uid("FETCH", ",".join(m["uid"] for m in known), "(UID FLAGS)"))
                    for item in data:
                        raw_flags = item[0] if isinstance(item, tuple) else item
                        if not isinstance(raw_flags, bytes):
                            continue
                        uid = re.search(rb"\bUID (\d+)", raw_flags)
                        if uid:
                            flags[uid[1].decode()] = tuple(v.decode("ascii", "replace") for v in imaplib.ParseFlags(raw_flags))
                low = int(snapshot.get("live_uid", max((int(m["uid"]) for m in known), default=0))) + 1
                high = int(values[b"UIDNEXT"]) - 1
                if low <= high:
                    criteria = f"UID {low}:{high}" + (" " + search_criteria(query, field) if query else "")
                    uids = [uid for uid in self._search(conn, criteria) if low <= int(uid) <= high]
                    added = self._fetch_uids(conn, uids[-limit:], validity, folder)
            return {"flags": flags, "checked_uids": [m["uid"] for m in known],
                    "added": added, "reset": reset, "uidvalidity": validity,
                    "live_uid": int(values[b"UIDNEXT"]) - 1, "total": int(values[b"MESSAGES"]),
                    "unread": int(values[b"UNSEEN"]), "checked_at": time.time()}

    def copy_message(self, header, destination):
        if destination == header["folder"] or not re.fullmatch(r"[1-9]\d*", str(header["uid"])):
            raise MailboxError("Choose another folder for this message.")
        with self._connection(header["folder"], header["uidvalidity"], write=True) as (conn, _, __):
            self._ok(conn.uid("COPY", header["uid"], folder_argument(destination)))
        return {"status": "copied"}

    def mark_folder_read(self, folder):
        """Explicit confirmed bulk action. No body fetch and no write replay."""
        with self._connection(folder, write=True) as (conn, _, validity):
            uids = self._search(conn, "UNSEEN")
            for offset in range(0, len(uids), 500):
                self._ok(conn.uid("STORE", ",".join(uids[offset:offset+500]), "+FLAGS.SILENT", "(\\Seen)"))
            raw = self._ok(conn.status(folder_argument(folder), "(UNSEEN)"))
            unread = re.search(rb"UNSEEN (\d+)", b" ".join(v for v in raw if isinstance(v, bytes)))
            return {"uids": uids, "uidvalidity": validity,
                    "unread": int(unread[1]) if unread else None}

    def _previews(self, conn, rows):
        """Bounded partial TEXT parts only, never attachment sections or full messages."""
        try:
            current = rows[-50:]
            data = self._ok(conn.uid("FETCH", ",".join(r["uid"] for r in current), "(UID BODYSTRUCTURE)"))
            groups, rowmap = {}, {r["uid"]: r for r in current}
            for item in data:
                if not isinstance(item, bytes):
                    continue  # Unusual literal BODYSTRUCTURE: leave snippet blank safely.
                uid, structure = re.search(rb"UID (\d+)", item), re.search(rb"BODYSTRUCTURE\s+", item, re.I)
                if not uid or not structure or uid[1].decode() not in rowmap:
                    continue
                try:
                    parts = mime_parts(_imap_tree(item[structure.end():]))
                    row = rowmap[uid[1].decode()]
                    row["has_attachments"] = any(p["attachment"] for p in parts)
                    readable = [p for p in parts if not p["attachment"]]
                    part = next((p for p in readable if p["content_type"] == "text/plain"), next(iter(readable), None))
                    if part:
                        groups.setdefault(part["section"], {})[row["uid"]] = part
                except (ValueError, TypeError):
                    continue
            deadline = time.monotonic() + 6
            for section, parts in list(groups.items())[:4]:
                if time.monotonic() > deadline:
                    break
                data = self._ok(conn.uid("FETCH", ",".join(parts), f"(UID BODY.PEEK[{section}]<0.1024>)"))
                for item in data:
                    if not isinstance(item, tuple):
                        continue
                    uid = re.search(rb"UID (\d+)", item[0])
                    if not uid or uid[1].decode() not in parts:
                        continue
                    uid = uid[1].decode()
                    part = parts[uid]
                    raw = decode_part(item[1][:1024], part)
                    try:
                        text = raw.decode(part["charset"], "replace")
                    except LookupError:
                        text = raw.decode("utf-8", "replace")
                    if part["content_type"] == "text/html":
                        text = html_to_text(text)
                    rowmap[uid]["snippet"] = " ".join(text.split())[:180]
        except Exception as error:
            LOGGER.info("Email previews unavailable (%s)", type(error).__name__)

    def related_headers(self, folder, identifiers, limit=100):
        criteria = self._related_criteria(identifiers)
        if not criteria:
            return []
        with self._connection(folder) as (conn, _, validity):
            uids = self._search(conn, criteria)
            return self._fetch_uids(conn, uids[-min(limit, 100):], validity, folder)

    @staticmethod
    def _related_criteria(identifiers):
        tokens = [i for i in dict.fromkeys(identifiers) if re.fullmatch(r"<[^<>\s\"\\]{1,250}>", i)][:8]
        if not tokens:
            return ""
        clauses = [f"HEADER {field} {_quoted_search(token)}" for token in tokens
                   for field in ("Message-ID", "References", "In-Reply-To")]
        return "OR " * (len(clauses)-1) + " ".join(clauses)

    def related_headers_many(self, folders, identifiers, limit=100):
        """One bounded authenticated read operation, never a persistent session socket."""
        criteria = self._related_criteria(identifiers)
        if not criteria:
            return []
        messages = []
        with self._connection(None) as (conn, _, __):
            for folder in list(dict.fromkeys(folders))[:3]:
                self._ok(conn.select(folder_argument(folder), readonly=True))
                _, response = conn.response("UIDVALIDITY")
                validity = response[0].decode("ascii")
                if not validity.isdigit():
                    raise MailboxError(SAFE_ERROR)
                uids = self._search(conn, criteria)
                messages.extend(self._fetch_uids(conn, uids[-min(limit, 100):], validity, folder))
        return messages

    def find_message_id(self, folder, message_id):
        if len(message_ids(message_id)) != 1 or message_ids(message_id)[0] != message_id:
            raise MailboxError("Invalid message identifier.")
        with self._connection(folder) as (conn, _, validity):
            uids = self._search(conn, f"HEADER Message-ID {_quoted_search(message_id)}")
            # IMAP HEADER searches are substring matches; verify the complete ID before deduplication.
            if len(uids) > 100:
                raise MailboxError("Too many matching message identifiers. Verify this operation in your mail client.")
            return [m["uid"] for m in self._fetch_uids(conn, uids, validity, folder) if m["message_id"] == message_id]

    def set_flag(self, header, flag, enabled):
        if flag not in {"\\Seen", "\\Flagged"} or not re.fullmatch(r"[1-9]\d*", str(header["uid"])):
            raise MailboxError("Unsupported message flag.")
        with self._connection(header["folder"], header["uidvalidity"], write=True) as (conn, _, __):
            self._ok(conn.uid("STORE", header["uid"], "+FLAGS.SILENT" if enabled else "-FLAGS.SILENT", f"({flag})"))
        return {"status": "updated"}

    def move_message(self, header, destination):
        if destination == header["folder"]:
            raise MailboxError("Message is already in this folder.")
        if not re.fullmatch(r"[1-9]\d*", str(header["uid"])):
            raise MailboxError("Invalid message identifier.")
        with self._connection(header["folder"], header["uidvalidity"], write=True) as (conn, _, __):
            if "MOVE" in self._capabilities(conn):
                self._ok(conn.uid("MOVE", header["uid"], folder_argument(destination)))
                return {"status": "moved"}
            # COPY-only fallback preserves the original. No broad EXPUNGE or destructive emulation.
            self._ok(conn.uid("COPY", header["uid"], folder_argument(destination)))
            return {"status": "copied", "notice": "Server MOVE is unavailable. Copied to the destination; original retained."}

    def delete_trash_messages(self, headers, *, trash_folder, folder_mapping=None):
        """Explicit, bounded UID deletion. Never fall back to mailbox-wide EXPUNGE."""
        if not headers or len(headers) > 1000:
            raise MailboxError("Select a Trash conversation before deleting.")
        validity = str(headers[0].get("uidvalidity", ""))
        if (not validity.isdigit() or any(h.get("folder") != trash_folder or
                str(h.get("uidvalidity")) != validity or
                not re.fullmatch(r"[1-9]\d*", str(h.get("uid", ""))) for h in headers)):
            raise MailboxError("Trash message identifiers changed. Refresh before deleting.")
        uids = sorted({str(h["uid"]) for h in headers}, key=int)
        with self._connection(trash_folder, validity, write=True) as (conn, _, __):
            folders = parse_folders(self._list_folders(conn))
            roles = folder_roles(folders, folder_mapping)
            target = next((f for f in folders if f["name"] == trash_folder), {})
            if (roles.get("trash") != trash_folder or trash_folder.upper() == "INBOX" or
                    target.get("role") not in {"", "trash"}):
                raise MailboxError("Permanent deletion is only available in the mapped Trash folder.")
            if not {"UIDPLUS", "IMAP4REV2"}.intersection(self._capabilities(conn)):
                raise MailboxError("This server does not support safe targeted deletion. Nothing was deleted; use your mailbox provider's Trash controls.")
            uid_set = ",".join(uids)
            present = set(self._search(conn, "UID " + uid_set)).intersection(uids)
            if not present:
                return {"status": "deleted", "uids": uids}
            uid_set = ",".join(sorted(present, key=int))
            already_deleted = set(self._search(conn, "UID " + uid_set + " DELETED"))
            added_flags = ",".join(sorted(present - already_deleted, key=int))
            expunge_started = False
            try:
                self._ok(conn.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Deleted)"))
                expunge_started = True
                self._ok(conn.uid("EXPUNGE", uid_set))
                if set(self._search(conn, "UID " + uid_set)).intersection(present):
                    raise MailboxError("Incomplete targeted deletion.")
            except Exception:
                # On rejection/partial completion, undo only flags set by this operation.
                # A dropped connection may prevent cleanup; never retry an expunge here.
                if added_flags:
                    try:
                        self._ok(conn.uid("STORE", added_flags, "-FLAGS.SILENT", "(\\Deleted)"))
                    except Exception:
                        pass
                if not expunge_started:
                    raise MailboxError("Could not permanently delete this email. Please try again.") from None
                raise MailboxError("Could not verify permanent deletion of every selected Trash message. Some may have been deleted. Refresh Trash before trying again.", code="delete_uncertain") from None
        return {"status": "deleted", "uids": uids}

    def append_message(self, folder, mime_bytes, *, draft=False):
        if len(mime_bytes) > 20 * 1024 * 1024:
            raise MailboxError("Message exceeds the 20 MB mailbox upload limit.", code="append_not_started")
        attempted = False
        try:
            target = folder_argument(folder)
            with self._connection(None, write=True) as (conn, _, __):
                attempted = True
                status, data = conn.append(target, "(\\Draft)" if draft else "(\\Seen)",
                                          imaplib.Time2Internaldate(time.time()), mime_bytes)
                if status in {"NO", "BAD"}:
                    raise MailboxError("Mailbox rejected the copy.", code="append_rejected")
                self._ok((status, data))
                return {"status": "appended", "append_uid": next((v.decode("ascii", "replace") for v in data if isinstance(v, bytes)), "")}
        except MailboxError as error:
            if not attempted:
                raise MailboxError("Could not connect to save the mailbox copy.", code="append_not_started") from None
            raise error

    def read_draft(self, header):
        with self._connection(header["folder"], header["uidvalidity"]) as (conn, _, __):
            if not str(header["uid"]).isdigit():
                raise MailboxError("Invalid draft identifier.")
            size_data = self._ok(conn.uid("FETCH", header["uid"], "(UID RFC822.SIZE)"))
            size = re.search(rb"RFC822.SIZE (\d+)", b" ".join(v for v in size_data if isinstance(v, bytes)))
            maximum = 20 * 1024 * 1024
            if not size or int(size[1]) > maximum:
                raise MailboxError("Draft is too large to edit here. Open it in your existing mail client.")
            data = self._ok(conn.uid("FETCH", header["uid"], f"(UID BODY.PEEK[]<0.{maximum+1}>)"))
            payloads = [v[1] for v in data if isinstance(v, tuple)]
            if len(payloads) != 1 or len(payloads[0]) > maximum:
                raise MailboxError("Draft could not be opened.")
            return payloads[0]

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
            raise MailboxError("This part is too large to open here. Open it in your existing mail client.")
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
