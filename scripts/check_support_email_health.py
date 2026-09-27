"""Explicit, read-only deployment diagnostic. Never imported by app startup.

Run in the deployment environment; prints only fixed stage/category labels and
timings. Uses one socket, verified TLS, EXAMINE and STATUS; never fetches mail.
"""
import imaplib
from pathlib import Path
import socket
import ssl
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support_email_provider import load_configuration, _failure, _close_resources


def check(configuration=None, emit=print):
    cfg = configuration or load_configuration()
    current = "configuration"
    started = time.monotonic()
    conn = None
    result = 0

    def stage(name, action):
        nonlocal current, started
        current, started = name, time.monotonic()
        value = action()
        emit(f"PASS {name} duration_ms={int((time.monotonic()-started)*1000)}")
        return value

    def ok(result):
        if result[0] != "OK":
            raise imaplib.IMAP4.error("Operation rejected")
        return result[1]

    class DiagnosticSSL(imaplib.IMAP4_SSL):
        def _connect(self):
            return stage("greeting", super()._connect)

        def _get_capabilities(self):
            return stage("capability", super()._get_capabilities)

        def _create_socket(self, timeout):
            stage("dns", lambda: socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM))
            raw = stage("tcp", lambda: socket.create_connection((self.host, self.port), timeout))
            try:
                return stage("tls", lambda: self.ssl_context.wrap_socket(raw, server_hostname=self.host))
            except BaseException:
                raw.close()
                raise

        def __init__(self):
            try:
                super().__init__(cfg.host, cfg.port, ssl_context=ssl.create_default_context(), timeout=cfg.timeout)
            except BaseException:
                _close_resources(self)
                raise

    try:
        if not cfg.configured:
            emit("FAIL configuration category=configuration duration_ms=0")
            return 1
        stage("configuration", lambda: True)
        conn = DiagnosticSSL()
        capabilities = stage("capability", lambda: ok(conn.capability()))
        emit("PASS idle_advertised" if b"IDLE" in b" ".join(capabilities).upper().split() else "PASS polling_fallback")
        stage("authentication", lambda: ok(conn.login(cfg.address, cfg.password)))
        stage("select", lambda: ok(conn.select('"INBOX"', readonly=True)))
        stage("status", lambda: ok(conn.status('"INBOX"', "(UNSEEN MESSAGES UIDNEXT UIDVALIDITY)")))
    except Exception as error:
        emit(f"FAIL {current} category={_failure(error, current).code} duration_ms={int((time.monotonic()-started)*1000)}")
        result = 1
    finally:
        if conn is not None:
            try:
                stage("logout", conn.logout)
            except Exception:
                emit("FAIL logout category=server_disconnect")
                result = 1
            finally:
                try:
                    conn.shutdown()
                except Exception:
                    pass
                _close_resources(conn)
    return result


if __name__ == "__main__":
    raise SystemExit(check())
