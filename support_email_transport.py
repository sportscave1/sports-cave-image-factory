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
