"""Email V2.2 timing probe: fabricated connections, no external services."""
import json
from statistics import mean
from time import perf_counter
from unittest.mock import patch

from support_email_provider import ImapProvider
from tests.test_support_email_live import LiveWire
from tests.test_support_email import CONFIG, header
from tests.profile_support_email import profile
import support_email_store as store


class FiftyMessages(LiveWire):
    def __init__(self):
        super().__init__()
        self.count = 50
        self.messages = {str(i): (() if i % 2 else ("\\Seen",)) for i in range(1, 51)}

    def status(self, folder, fields):
        self.calls.append(("status", folder, fields))
        return "OK", [b'INBOX (UNSEEN 25 MESSAGES 50 UIDNEXT 51 UIDVALIDITY 500)']


def measure():
    wire = FiftyMessages()
    adapter = ImapProvider(CONFIG, connection_factory=lambda *a, **k: wire)
    snapshot = {"messages": [header(str(i)) for i in range(1, 51)], "uidvalidity": "500", "live_uid": 50}
    samples = []
    for _ in range(50):
        wire.calls.clear()
        start = perf_counter()
        adapter.live_changes("INBOX", snapshot)
        samples.append((perf_counter()-start)*1000)
    with patch.object(store, 'audit'):
        opened = profile()
    return {"fixture_only": True, "network_latency_included": False, "loaded_uids": 50,
            "poll_samples": len(samples), "mean_poll_ms": round(mean(samples), 3),
            "max_poll_ms": round(max(samples), 3), "commands": wire.calls,
            "body_fetches": sum('BODY' in str(c) for c in wire.calls),
            "attachment_fetches": 0, "reopen": opened['immediate_reopen'],
            "cold_with_simulated_240ms_body": opened['cold']}


if __name__ == '__main__':
    print(json.dumps(measure(), indent=2))
