"""One bounded, hidden Docker exec channel per verified preview container."""
import json
import queue
import subprocess
import threading
import time
import studio

STREAM = """import sys,json,urllib.request,urllib.error
for line in sys.stdin.buffer:
    try:
        if len(line)>12000:raise ValueError('Oversized event')
        r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8877',data=line,headers={'Content-Type':'application/json'}),timeout=15)
        payload=r.read(2000001)
        if len(payload)>2000000:raise ValueError('Oversized frame')
        result={'ok':True,'result':json.loads(payload)}
    except Exception as error:
        result={'ok':False,'error':str(error)[:600]}
    sys.stdout.write(json.dumps(result,separators=(',',':'))+'\\n');sys.stdout.flush()
"""


class RelayTransportError(RuntimeError):
    pass


class Relay:
    def __init__(self, container, context):
        args = ['docker', '--context', context, 'exec', '-i', container, 'python', '-B', '-c', STREAM]
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, **studio.quiet_process())
        self.responses = queue.Queue()
        self.errors = bytearray()
        self.lock = threading.Lock()
        def read():
            while True:
                line = self.process.stdout.readline(2001000)
                if not line:
                    self.responses.put(RelayTransportError('Preview relay closed. Retry the explicit operation.'))
                    return
                if len(line) >= 2001000 or not line.endswith(b'\n'):
                    self.responses.put(RelayTransportError('Oversized preview relay response.'))
                    return
                self.responses.put(line)
        def errors():
            while chunk := self.process.stderr.read(256):
                self.errors.extend(chunk)
                del self.errors[:-2000]
        self.reader=threading.Thread(target=read, daemon=True)
        self.error_reader=threading.Thread(target=errors, daemon=True)
        self.reader.start();self.error_reader.start()

    def request(self, data, timeout=20):
        body = json.dumps(data).encode()
        if len(body) > 11000:
            raise ValueError('Event is too large.')
        with self.lock:
            try:
                deadline=time.monotonic()+timeout
                sent=queue.Queue()
                def write():
                    try:
                        self.process.stdin.write(body+b'\n');self.process.stdin.flush()
                        sent.put(None)
                    except OSError as error:sent.put(error)
                writer=threading.Thread(target=write,daemon=True);writer.start()
                failure=sent.get(timeout=timeout)
                if failure:raise failure
                response = self.responses.get(timeout=max(.001,deadline-time.monotonic()))
                if isinstance(response, Exception):
                    raise response
                result = json.loads(response)
                if not result.get('ok'):
                    raise RuntimeError(result.get('error', 'Preview relay rejected the operation.'))
                return result['result']
            except (OSError, queue.Empty, ValueError) as exc:
                self.close()
                raise RelayTransportError('Preview relay failed or timed out; the last frame and source are preserved. '
                                   + bytes(self.errors).decode(errors='replace')[-600:]) from exc

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        self.reader.join(timeout=1);self.error_reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:stream.close()
            except OSError:pass
