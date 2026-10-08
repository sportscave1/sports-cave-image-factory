"""Deterministic offline read round-trip benchmark, no database connection."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from os_accounts import PostgresAccountStore


class Cursor:
    def __init__(self):
        self.calls = 0
        self.sql = ""

    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, sql, *_):
        self.calls += 1
        self.sql = sql
        time.sleep(.02)
    def fetchone(self): return self.fetchall()[0]
    def fetchall(self):
        if self.sql.lstrip().startswith("SELECT page_key"):
            return [{"page_key": "dashboard"}]
        return [{"id": str(i), "username": f"fixture-{i}", "role": "worker", "is_active": True,
                 "page_permissions": ["dashboard"], "_page_permissions": ["dashboard"]} for i in range(20)]


class Connection:
    def __init__(self, cursor): self.cur = cursor
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def cursor(self): return self.cur


def main():
    store = PostgresAccountStore()
    results = {"simulated_round_trip_ms": 20, "users": 20}
    for method, args in (("get_user", ("fixture",)), ("list_users", ())):
        cur = Cursor()
        with patch.object(store, "ensure_schema"), patch.object(store, "_connect", return_value=Connection(cur)):
            start = time.perf_counter()
            getattr(store, method)(*args)
            results[method] = {"queries": cur.calls, "ms": round((time.perf_counter()-start)*1000, 2)}
    print(json.dumps(results))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
