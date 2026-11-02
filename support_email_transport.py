"""IMAP-only transport diagnostics; preserve resolver order and verified TLS.

Do not log addresses, exception strings or authentication. Report every address
attempt: socket.create_connection otherwise discards all but the last error.
"""
import logging
import socket
import time

LOGGER = logging.getLogger(__name__)


def failed(error, stage, started, family="none"):
    error.email_stage = stage
    LOGGER.warning("email_imap_transport_failure stage=%s family=%s type=%s errno=%s duration_ms=%d",
                   stage, family, type(error).__name__,
                   error.errno if isinstance(getattr(error, 'errno', None), int) else None,
                   (time.monotonic()-started)*1000)


def connect_tcp(host, port, timeout):
    started = time.monotonic()
    try:
        addresses = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except OSError as error:
        failed(error, 'dns', started)
        raise
    last_error = timeout_error = None
    deadline = time.monotonic() + timeout
    # A black-holed IPv6 endpoint must leave time for resolved IPv4 addresses.
    # Keep DNS/resolver order and the overall deadline, sharing this small budget
    # across all IPv6 attempts before the first IPv4 attempt.
    has_ipv4 = any(item[0] == socket.AF_INET for item in addresses)
    ipv4_attempted = False
    ipv6_budget = min(1.0, timeout / 4)
    for family, kind, protocol, _, address in addresses:
        wire = None
        started = time.monotonic()
        remaining = deadline - started
        if remaining <= 0:
            # No socket attempt occurred for this address. Do not mislabel a
            # consumed shared deadline as an independent IPv6 route failure.
            LOGGER.info('email_imap_transport_skipped stage=tcp family=%s reason=deadline',
                        'ipv6' if family == socket.AF_INET6 else 'ipv4')
            last_error = timeout_error or TimeoutError('Mailbox connect deadline exceeded')
            break
        reserve_ipv4 = family == socket.AF_INET6 and has_ipv4 and not ipv4_attempted
        if reserve_ipv4:
            if ipv6_budget <= 0:
                continue
            remaining = min(remaining, ipv6_budget)
        if family == socket.AF_INET:ipv4_attempted = True
        try:
            wire = socket.socket(family, kind, protocol)
            wire.settimeout(remaining)
            wire.connect(address)
            return wire
        except BaseException as error:
            if wire is not None:
                wire.close()
            if not isinstance(error, OSError):
                raise
            failed(error, 'tcp', started, 'ipv6' if family == socket.AF_INET6 else 'ipv4')
            last_error = error
            if isinstance(error, TimeoutError):timeout_error = error
        finally:
            if reserve_ipv4:ipv6_budget = max(0, ipv6_budget - (time.monotonic()-started))
    if timeout_error is not None:
        raise timeout_error  # Do not mask IPv4 timeout with the final unroutable IPv6 address.
    if last_error is not None:
        raise last_error
    raise OSError('No resolved mailbox endpoints')


def connect_tls(host, port, timeout, context):
    raw = connect_tcp(host, port, timeout)
    started = time.monotonic()
    try:
        return context.wrap_socket(raw, server_hostname=host)
    except BaseException as error:
        raw.close()
        if isinstance(error, Exception):
            failed(error, 'tls', started)
        raise
