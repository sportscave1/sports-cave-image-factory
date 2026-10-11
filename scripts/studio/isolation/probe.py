"""Inert container-boundary probes. No application imports or production targets."""
import ctypes
import http.client
import imaplib
import json
import os
from pathlib import Path
import smtplib
import socket
import subprocess
import sys
import urllib.request

checks = {}
def check(name, value):
    checks[name] = bool(value)

def denied(name, operation):
    try:
        result = operation()
        if hasattr(result, "close"):
            result.close()
    except (OSError, ValueError, RuntimeError) as exc:
        checks[name] = True
    else:
        checks[name] = False

def inaccessible(path):
    try:
        return not Path(path).exists()
    except PermissionError:
        return True

def run(target, child=False):
    import psycopg
    check("non_root", os.getuid() == 65532)
    status = Path("/proc/self/status").read_text()
    check("capabilities_dropped", "CapEff:\t0000000000000000" in status)
    check("no_new_privileges", "NoNewPrivs:\t1" in status)
    check("seccomp_enabled", "Seccomp:\t2" in status)
    check("only_loopback", {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"})
    check("no_ipv4_route", len(Path("/proc/net/route").read_text().splitlines()) == 1)
    check("no_credentials_environment", not any(k in os.environ for k in
        ("DATABASE_URL", "SUPABASE_URL", "AWS_ACCESS_KEY_ID", "SHOPIFY_ACCESS_TOKEN",
         "META_ACCESS_TOKEN", "RESEND_API_KEY", "SSH_AUTH_SOCK", "DOCKER_HOST", "STUDIO_HOST_CANARY")))
    check("no_host_files", all(inaccessible(p) for p in
        ("/mnt/c", "/host", "/app", "/root/.aws", "/root/.ssh", "/root/.docker", "/var/run/docker.sock",
         "/run/desktop", "/.env", "/.git")))
    denied("root_filesystem_read_only", lambda: Path("/forbidden").write_text("synthetic"))
    denied("proc_environment_denied", lambda: Path("/proc/1/root/root/.aws/credentials").read_bytes())
    denied("tcp", lambda: socket.create_connection((target, 8123), timeout=2))
    denied("http", lambda: urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        "http://" + target + ":8123", timeout=2))
    denied("smtp", lambda: smtplib.SMTP(target, 8123, timeout=2))
    denied("imap", lambda: imaplib.IMAP4(target, port=8123, timeout=2))
    try:
        psycopg.connect(host=target, port=8123, user="synthetic", dbname="synthetic",
                        password="synthetic", connect_timeout=2)
    except psycopg.OperationalError:
        check("native_libpq", True)
    else:
        check("native_libpq", False)
    def udp():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"synthetic", (target, 8123))
    denied("udp", udp)
    def ipv6():
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("2001:db8::1", 8123))
    denied("ipv6", ipv6)
    denied("dns", lambda: socket.getaddrinfo("studio-canary.invalid", 8123))
    # Direct libc socket/connect bypasses Python socket wrappers.
    libc = ctypes.CDLL(None, use_errno=True)
    class Address(ctypes.Structure):
        _fields_ = [("family", ctypes.c_ushort), ("port", ctypes.c_ushort),
                    ("address", ctypes.c_ubyte*4), ("padding", ctypes.c_ubyte*8)]
    addr = Address(socket.AF_INET, socket.htons(8123),
                   (ctypes.c_ubyte*4)(*socket.inet_aton(target)), (ctypes.c_ubyte*8)())
    fd = libc.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    result = libc.connect(fd, ctypes.byref(addr), ctypes.sizeof(addr))
    error = ctypes.get_errno()
    libc.close(fd)
    check("native_libc_connect", result == -1 and error in (101, 113))
    path = Path("/tmp/synthetic.json")
    path.write_text('{"synthetic":true}')
    check("temporary_storage_works", json.loads(path.read_text())["synthetic"])
    if not child:
        result = subprocess.run([sys.executable, "-B", __file__, target, "--child"],
                                capture_output=True, text=True, timeout=25)
        check("child_process_inherits_boundary", result.returncode == 0 and json.loads(result.stdout)["passed"])
        # A shell and grandchild cannot escape by starting another interpreter.
        result = subprocess.run(["/bin/sh", "-c", 'exec python -B "$1" "$2" --child', "probe", __file__, target],
                                capture_output=True, text=True, timeout=25)
        check("shell_grandchild_inherits_boundary", result.returncode == 0 and json.loads(result.stdout)["passed"])
    print(json.dumps({"passed": all(checks.values()), "checks": checks, "libpq_version": psycopg.pq.version()}))
    return 0 if all(checks.values()) else 1

if __name__ == "__main__":
    sys.exit(run(sys.argv[1], "--child" in sys.argv))
