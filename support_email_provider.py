"""Live IMAP adapter. Reads are non-mutating; writes require explicit method calls."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser, BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
import hashlib
import base64
import imaplib
import logging
import os
import re
import ssl
import time
from typing import Protocol
from urllib.parse import urlsplit


LOGGER = logging.getLogger(__name__)
SAFE_ERROR = "Email connection failed. Check Render email credentials."
MAX_TEXT_BYTES = 512 * 1024
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
HEADER_FIELDS = "FROM REPLY-TO TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES CONTENT-TYPE"


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
    def related_headers(self, folder, identifiers, limit=100): ...
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
    """Only unique SPECIAL-USE attributes or an explicit mapping to an observed LIST name."""
    names = {f["name"] for f in folders}
    roles = {}
    for role in ("inbox", "sent", "drafts", "archive", "junk", "trash"):
        matches = [f["name"] for f in folders if f["role"] == role]
        if len(matches) == 1:
            roles[role] = matches[0]
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


class ImapProvider:
    def __init__(self, configuration, *, connection_factory=None):
        self.configuration = configuration
        self.connection_factory = connection_factory or imaplib.IMAP4_SSL

    @contextmanager
    def _connection(self, folder="INBOX", expected_validity=None, *, write=False):
        conn = None
        try:
            cfg = self.configuration
            if not cfg.configured:
                raise MailboxError("Email is not configured. Add the secure IMAP environment variables.")
            argument = folder_argument(folder) if folder is not None else None
            conn = self.connection_factory(cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=cfg.timeout)
            conn.debug = 0
            self._ok(conn.login(cfg.address, cfg.password))
            count, uidvalidity = 0, ""
            if argument is not None:
                count = int(self._ok(conn.select(argument, readonly=not write))[0])
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
                    conn.logout()  # Never CLOSE/EXPUNGE, even after a write.
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

    def discover_folders(self):
        with self._connection(None) as (conn, _, __):
            folders = parse_folders(self._ok(conn.list()))
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
            return {"messages": rows, "total": count, "matched": matched, "uidvalidity": validity,
                    "refreshed_at": datetime.now(timezone.utc), "has_more": matched > limit}

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
        tokens = [i for i in dict.fromkeys(identifiers) if re.fullmatch(r"<[^<>\s\"\\]{1,250}>", i)][:8]
        if not tokens:
            return []
        clauses = [f"HEADER {field} {_quoted_search(token)}" for token in tokens
                   for field in ("Message-ID", "References", "In-Reply-To")]
        criteria = "OR " * (len(clauses)-1) + " ".join(clauses)
        with self._connection(folder) as (conn, _, validity):
            uids = self._search(conn, criteria)
            return self._fetch_uids(conn, uids[-min(limit, 100):], validity, folder)

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

    def append_message(self, folder, mime_bytes, *, draft=False):
        if len(mime_bytes) > 20 * 1024 * 1024:
            raise MailboxError("Message exceeds the 20 MB mailbox upload limit.")
        with self._connection(None) as (conn, _, __):
            data = self._ok(conn.append(folder_argument(folder), "(\\Draft)" if draft else "(\\Seen)",
                                       imaplib.Time2Internaldate(time.time()), mime_bytes))
            return {"status": "appended", "append_uid": next((v.decode("ascii", "replace") for v in data if isinstance(v, bytes)), "")}

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
