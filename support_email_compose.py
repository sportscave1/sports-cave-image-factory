"""Safe human-authored MIME, signatures and compose/reply/forward models. No I/O."""
import base64
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, formataddr, getaddresses
from html import escape
from html.parser import HTMLParser
import mimetypes
import re
from urllib.parse import urlparse
import uuid

from support_email_provider import html_to_text, message_ids, addresses

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 14 * 1024 * 1024
MAX_MIME_BYTES = 20 * 1024 * 1024
MAX_BODY_CHARS = 250_000
SIGNATURE_KEYS = ("company", "nathan", "reina", "none")


class ComposeError(ValueError):
    pass


def safe_url(value):
    value = str(value or "").strip()
    if any(ord(c) < 32 for c in value) or any(c in value for c in ('"', '<', '>', '\\')):
        return ""
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        return ""
    if parsed.scheme.lower() in {"http", "https"} and hostname and not parsed.username and not parsed.password:
        return value
    if parsed.scheme.lower() == "mailto" and re.fullmatch(r"[^\s?@]+@[^\s?@]+", parsed.path):
        return value
    return ""


class _SafeHTML(HTMLParser):
    tags = {"p", "div", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "blockquote", "a"}
    blocked = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.hidden = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.hidden.append(tag)
            return
        if self.hidden or tag not in self.tags:
            return
        attr = ""
        if tag == "a":
            url = safe_url(dict(attrs).get("href"))
            if url:
                attr = f' href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer"'
        self.out.append(f"<{tag}{attr}>")
        if tag != "br":
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]
            return
        if not self.hidden and tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.out.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, text):
        if not self.hidden:
            self.out.append(escape(text))

    def finish(self):
        for tag in reversed(self.stack):
            self.out.append(f"</{tag}>")
        return "".join(self.out)


def sanitize_html(value):
    value = str(value or "")
    if len(value) > MAX_BODY_CHARS:
        raise ComposeError("Email text is too large. Keep the body below 250,000 characters.")
    parser = _SafeHTML()
    parser.feed(value)
    return parser.finish()


def plain_html(value):
    return "<p>" + escape(str(value)).replace("\n", "<br>") + "</p>"


def readable_html(text):
    """Only escaped text plus allowlisted external anchors; no automatic network resources."""
    parts, start = [], 0
    for match in re.finditer(r"https?://[^\s<>\"']+", text):
        url = match[0].rstrip(".,);]")
        parts.append(escape(text[start:match.start()]))
        if safe_url(url):
            parts.append(f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(url)}</a>')
            parts.append(escape(match[0][len(url):]))
        else:
            parts.append(escape(match[0]))
        start = match.end()
    parts.append(escape(text[start:]))
    return "".join(parts).replace("\n", "<br>")


def split_quote(text):
    lines = str(text or "").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if i > 0 and (line.startswith(">") or re.match(r"On .+wrote:\s*$|[-_]{3,}\s*(Original|Forwarded) [Mm]essage", line.strip())):
            return "".join(lines[:i]).strip(), "".join(lines[i:]).strip()
    return str(text or ""), ""


def recipient_list(value):
    if not isinstance(value, str) or len(value) > 4000 or any(c in value for c in "\r\n\x00"):
        raise ComposeError("Enter valid recipient addresses without line breaks.")
    try:
        parsed = getaddresses([value.replace(";", ",")], strict=True)
    except TypeError:
        parsed = getaddresses([value.replace(";", ",")])
    result = []
    for name, address in parsed:
        if not address and not value.strip():
            continue
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", address):
            raise ComposeError("One or more recipient addresses are invalid. Use complete email addresses.")
        result.append({"name": name, "email": address.casefold()})
    return result


def deduplicate(groups, *, exclude=()):
    seen = {v.casefold() for v in exclude}
    output = []
    for group in groups:
        current = []
        for person in group:
            address = person["email"].casefold()
            if address not in seen:
                seen.add(address)
                current.append(person)
        output.append(current)
    return output


def address_text(people):
    return ", ".join(formataddr((p["name"], p["email"]), charset="utf-8") for p in people)


def reply_recipients(header, mailbox, *, reply_all=False):
    own = mailbox.casefold()
    if header["sender"]["email"].casefold() == own:
        main = list(header["to"])
    else:
        main = list(header.get("reply_to") or [header["sender"]])
        if reply_all:
            main += [header["sender"], *header["to"]]
    to, cc = deduplicate([main, header["cc"] if reply_all else []], exclude=[own])
    return address_text(to), address_text(cc)


def default_settings():
    signatures = {}
    for key, name, role in (("company", "Sports Cave", "Limited Edition Sports Wall Art"),
                            ("nathan", "Nathan", "Sports Cave"), ("reina", "Reina", "Customer Support · Sports Cave")):
        signatures[key] = {"label": {"company": "Company default", "nathan": "Nathan", "reina": "Reina"}[key],
                           "html": f"<p>Kind regards,<br><strong>{name}</strong><br>{role}</p>"}
        signatures[key]["text"] = html_to_text(signatures[key]["html"])
    return {"sender_name": "Sports Cave", "signatures": signatures, "folder_mapping": {}, "sent_policy": "verify"}


def selected_signature(settings, user, preference=None):
    if preference in SIGNATURE_KEYS:
        return preference
    name = str(user.get("username") or user.get("display_name") or "").casefold().split(" ")[0]
    return name if name in ("nathan", "reina") else "company"


def new_draft(mailbox, *, mode="new", header=None, text="", signature="company"):
    draft = {"id": str(uuid.uuid4()), "operation_id": str(uuid.uuid4()), "mode": mode,
             "to": "", "cc": "", "bcc": "", "subject": "", "html": "<p><br></p>",
             "signature": signature, "quote_html": "", "include_quote": mode != "new",
             "in_reply_to": "", "references": [], "attachments": [], "revision": 0, "mailbox_ref": None}
    if header:
        draft["subject"] = header["subject"]
        if mode in {"reply", "reply_all"}:
            draft["to"], draft["cc"] = reply_recipients(header, mailbox, reply_all=mode == "reply_all")
            if not re.match(r"^\s*re\s*:", draft["subject"], re.I):
                draft["subject"] = "Re: " + draft["subject"]
            draft["in_reply_to"] = header["message_id"]
            draft["references"] = list(dict.fromkeys([*header["references"], *header["in_reply_to"], header["message_id"]]))[-30:]
        elif mode == "forward":
            if not re.match(r"^\s*fw(?:d)?\s*:", draft["subject"], re.I):
                draft["subject"] = "Fwd: " + draft["subject"]
        context = (f"From: {address_text([header['sender']])}\nDate: {header.get('date') or header.get('received_at')}\n"
                   f"To: {address_text(header['to'])}\nCC: {address_text(header['cc'])}\nSubject: {header['subject']}\n\n{text}")
        draft["quote_html"] = "<blockquote>" + plain_html(context) + "</blockquote>"
    return draft


def attachment_from_upload(filename, encoded):
    if not isinstance(encoded, str) or len(encoded) > (MAX_FILE_BYTES * 4 // 3 + 16):
        raise ComposeError("Attachment too large. Maximum file size is 10 MB.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ComposeError("Attachment could not be read.") from None
    return make_attachment(filename, data)


def make_attachment(filename, data):
    filename = re.sub(r'[\\/\x00-\x1f]', "_", str(filename))[:200]
    if not filename or len(data) > MAX_FILE_BYTES:
        raise ComposeError("Attachment too large or filename missing. Maximum file size is 10 MB.")
    return {"id": str(uuid.uuid4()), "filename": filename, "data": bytes(data),
            "content_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}


def add_attachment(draft, attachment):
    if len(draft["attachments"]) >= 15 or sum(len(a["data"]) for a in draft["attachments"]) + len(attachment["data"]) > MAX_TOTAL_ATTACHMENT_BYTES:
        raise ComposeError("Attachments exceed the 14 MB total limit (15 files maximum).")
    draft["attachments"].append(attachment)


def build_mime(draft, mailbox, sender_name, signatures, *, as_draft=False):
    groups = deduplicate([recipient_list(str(draft.get(key) or "")) for key in ("to", "cc", "bcc")])
    recipients = [p["email"] for group in groups for p in group]
    if not as_draft and not recipients:
        raise ComposeError("Add at least one recipient.")
    if len(recipients) > 25:
        raise ComposeError("Email is for individual correspondence. Maximum 25 recipients.")
    subject = str(draft.get("subject") or "")
    if any(c in subject + sender_name for c in "\r\n\x00") or len(subject) > 998:
        raise ComposeError("Invalid subject or sender name.")
    if not subject.strip() and not as_draft:
        raise ComposeError("Add a subject before sending.")
    try:
        operation = str(uuid.UUID(draft["operation_id"]))
    except (ValueError, KeyError):
        raise ComposeError("This compose session is invalid. Open a new draft.") from None
    message_id = f"<sc.{operation}{'.draft.' + str(draft['revision']) if as_draft else ''}@{mailbox.split('@')[-1]}>"
    html = sanitize_html(draft.get("html", ""))
    signature = signatures.get(draft.get("signature"), {})
    if signature:
        html += sanitize_html(signature.get("html", ""))
    if draft.get("include_quote"):
        html += sanitize_html(draft.get("quote_html", ""))
    msg = EmailMessage(policy=policy.SMTP)
    msg["Message-ID"] = message_id
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["From"] = formataddr((sender_name, mailbox), charset="utf-8")
    for name, people in zip(("To", "Cc", "Bcc"), groups):
        if people and (name != "Bcc" or as_draft):
            msg[name] = address_text(people)
    msg["Subject"] = subject
    if draft.get("mode") in {"reply", "reply_all"}:
        reply = message_ids(draft.get("in_reply_to"))
        refs = tuple(dict.fromkeys(i for r in draft.get("references", []) for i in message_ids(r)))
        if reply:
            msg["In-Reply-To"] = reply[-1]
        if refs:
            msg["References"] = " ".join(refs[-30:])
    if as_draft:
        msg["X-Sports-Cave-Draft-ID"] = str(uuid.UUID(draft["id"]))
    msg.set_content(html_to_text(html))
    msg.add_alternative(html, subtype="html")
    total = 0
    for attachment in draft["attachments"]:
        total += len(attachment["data"])
        if len(attachment["data"]) > MAX_FILE_BYTES or total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise ComposeError("Attachments exceed the message limit.")
        content_type = attachment["content_type"].split("/", 1)
        if len(content_type) != 2 or not all(re.fullmatch(r"[\w.+-]+", p) for p in content_type):
            content_type = ["application", "octet-stream"]
        msg.add_attachment(attachment["data"], maintype=content_type[0], subtype=content_type[1], filename=attachment["filename"])
    raw = msg.as_bytes()
    if len(raw) > MAX_MIME_BYTES:
        raise ComposeError("Message exceeds the 20 MB encoded limit. Remove an attachment.")
    return {"bytes": raw, "message_id": message_id, "recipients": recipients}


def edit_mailbox_draft(raw, mailbox, reference):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    draft = new_draft(mailbox, signature="none")
    draft.update(to=address_text(addresses(message.get_all("To", []))), cc=address_text(addresses(message.get_all("Cc", []))),
                 bcc=address_text(addresses(message.get_all("Bcc", []))), subject=str(message.get("Subject", "")),
                 mailbox_ref=dict(reference))
    body = message.get_body(preferencelist=("html", "plain"))
    if body:
        text = body.get_content()
        draft["html"] = sanitize_html(text) if body.get_content_type() == "text/html" else plain_html(text)
    draft["in_reply_to"] = next(iter(message_ids(message.get("In-Reply-To"))), "")
    draft["references"] = list(message_ids(message.get("References")))
    if draft["in_reply_to"]:
        draft["mode"] = "reply"
    for part in message.walk():
        if part.get_content_disposition() == "attachment" or part.get_filename():
            if part.is_multipart():
                raise ComposeError("This draft contains an attached message. Edit it in your existing mail client.")
            add_attachment(draft, make_attachment(part.get_filename() or "attachment", part.get_payload(decode=True) or b""))
    return draft
