"""Loopback-only PostgreSQL protocol delay for synthetic performance checks.

Adds a fixed one-way delay while continuously reading and scheduling packets.
Protocol frames are counted, not delayed separately: pipelined Flush/Sync
frames must be able to travel together. This is not a WAN/TLS/load emulator.
"""
from contextlib import contextmanager
import socket
import socketserver
import queue
import struct
import threading
import time
from urllib.parse import urlsplit


@contextmanager
def delayed_database(dsn, delay_ms):
    parsed = urlsplit(dsn)
    if parsed.hostname != "127.0.0.1":
        raise ValueError("Only an explicit loopback test database is allowed.")
    records, sockets = [], []
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            remote=socket.create_connection(("127.0.0.1",parsed.port),timeout=5)
            remote.settimeout(None)
            sockets.extend([self.request,remote])
            record=dict(startups=0,syncs=0,flushes=0,simple_queries=0)
            records.append(record)
            pending=queue.Queue()
            def outgoing():
                try:
                    while (item:=pending.get()) is not None:
                        ready,data=item
                        time.sleep(max(0,ready-time.perf_counter()))
                        remote.sendall(data)
                except OSError:
                    pass
            forward=threading.Thread(target=outgoing,daemon=True)
            forward.start()
            def incoming():
                try:
                    while data:=remote.recv(65536):
                        self.request.sendall(data)
                except OSError:
                    pass
                finally:
                    try:self.request.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
            back=threading.Thread(target=incoming,daemon=True)
            back.start()
            buffer=b""
            startup=True
            try:
                while data:=self.request.recv(65536):
                    pending.put((time.perf_counter()+delay_ms/1000,data))
                    buffer+=data
                    while True:
                        if startup:
                            if len(buffer)<4:break
                            length=struct.unpack("!I",buffer[:4])[0]
                            key="startups"
                        else:
                            if len(buffer)<5:break
                            length=1+struct.unpack("!I",buffer[1:5])[0]
                            key={b"S":"syncs",b"H":"flushes",b"Q":"simple_queries"}.get(buffer[:1])
                        if len(buffer)<length:break
                        message,buffer=buffer[:length],buffer[length:]
                        if key:
                            record[key]+=1
                        startup=False
            except OSError:
                pass
            finally:
                pending.put(None)
                forward.join(timeout=1)
                try:remote.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                remote.close()
                back.join(timeout=1)
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads=True
    server=Server(("127.0.0.1",0),Handler)
    runner=threading.Thread(target=server.serve_forever,daemon=True)
    runner.start()
    try:
        yield f"postgresql://postgres@127.0.0.1:{server.server_address[1]}/postgres?sslmode=disable",records
    finally:
        server.shutdown()
        server.server_close()
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            sock.close()
        runner.join(timeout=2)
