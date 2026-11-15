"""Pure threading, conservative order matching and per-session display cache."""
from datetime import datetime, timezone
import hashlib
import re
import time
import uuid

from support_email_provider import MailboxError, SAFE_ERROR


CACHE_TTL = 20
STATUSES = ("Needs Reply", "Waiting on Customer", "Waiting on Sports Cave", "Resolved")


def normalize_subject(subject):
    return re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", str(subject or "").strip(), flags=re.I).strip().casefold()


def thread_hash(mailbox, identity):
    return hashlib.sha256((mailbox.casefold() + "\n" + identity).encode()).hexdigest()


def timestamp(message):
    return (message.get("received_at") or message.get("date") or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp()


def message_identity(message):
    return message.get("message_id") or f"uid:{message['folder']}:{message['uidvalidity']}:{message['uid']}"


def is_customer(message, mailbox):
    return message["sender"]["email"].casefold() != mailbox.casefold()


def participants(message, mailbox):
    return tuple(sorted({p["email"].casefold() for p in [message["sender"], *message["to"], *message["cc"]]
                         if p["email"] and p["email"].casefold() != mailbox.casefold()}))


def build_threads(messages, mailbox):
    messages=list({(m['folder'],str(m['uidvalidity']),str(m['uid'])):m for m in messages}.values())
    parents, ancestry = {}, {}

    def root(key):
        parents.setdefault(key, key)
        path = []
        while parents[key] != key:
            path.append(key)
            key = parents[key]
        for item in path:
            parents[item] = key
        return key

    def join(a, b):
        a, b = root(a), root(b)
        if a != b:
            parents[max(a, b)] = min(a, b)

    for message in messages:
        identity = message_identity(message)
        root(identity)
        refs = list(dict.fromkeys([*(message.get("references") or ()), *(message.get("in_reply_to") or ())]))
        chain = [*refs, identity]
        for a, b in zip(chain, chain[1:]):
            join(a, b)
            ancestry.setdefault(b, set()).add(a)

    # Fallback only for messages with no reply relationship headers, and exactly one
    # same-subject/same-participant original within seven days. Separate roots stay separate.
    for message in messages:
        if message.get("references") or message.get("in_reply_to"):
            continue
        subject = normalize_subject(message["subject"])
        if not subject or not re.match(r"^\s*(?:re|fw|fwd)\s*:", message["subject"], re.I):
            continue
        candidates = [m for m in messages if m is not message
                      and not m.get("references") and not m.get("in_reply_to")
                      and not re.match(r"^\s*(?:re|fw|fwd)\s*:", m["subject"], re.I)
                      and normalize_subject(m["subject"]) == subject
                      and participants(m, mailbox) == participants(message, mailbox)
                      and participants(message, mailbox)
                      and 0 <= timestamp(message) - timestamp(m) <= 7 * 86400]
        if len(candidates) == 1:
            a, b = message_identity(candidates[0]), message_identity(message)
            join(a, b)
            ancestry.setdefault(b, set()).add(a)

    grouped = {}
    for message in messages:
        grouped.setdefault(root(message_identity(message)), []).append(message)
    threads = []
    for group_root, members in grouped.items():
        identifiers = {identifier for identifier in parents if root(identifier) == group_root}
        roots = sorted(identifier for identifier in identifiers if not ancestry.get(identifier))
        canonical = (roots or sorted(identifiers))[0]
        members.sort(key=lambda m: (timestamp(m), int(m["uid"])))
        customers = [m for m in members if is_customer(m, mailbox)]
        customer = customers[-1]["sender"] if customers else next(
            (p for m in members for p in m["to"] if p["email"].casefold() != mailbox.casefold()),
            {"name": "Sports Cave", "email": mailbox})
        threads.append({"thread_key": thread_hash(mailbox, canonical),
                        "aliases": tuple(sorted(thread_hash(mailbox, i) for i in identifiers)),
                        "messages": members, "customer": customer, "subject": members[0]["subject"],
                        "last_activity": max(timestamp(m) for m in members),
                        "last_customer_activity": max(timestamp(m) for m in (customers or members)),
                        "last_activity_at": members[-1].get("received_at") or members[-1].get("date"),
                        "last_customer_at": (customers or members)[-1].get("received_at") or (customers or members)[-1].get("date"),
                        "unread": sum(m["unread"] for m in members)})
    return sorted(threads, key=lambda t: t["last_customer_activity"], reverse=True)
