"""Real loopback disconnect during a chunk body preserves committed offsets."""
import hashlib
import socket
import time
from urllib.parse import urlsplit
import requests
from tests.test_auto_editions_jobs import database
from tests.test_companion_phase3 import env, http_receiver, padded
from companion_package_identity import CHUNK


def test_disconnect_mid_body_retries_only_unconfirmed_chunk(env,monkeypatch):
    e=env;padded(e)
    with http_receiver(e,monkeypatch) as (base,token,seen):
        headers={'X-Sports-Cave-Preparation-Host':token,'X-Sports-Cave-Transfer-Secret':'fixture'}
        response=requests.post(base+'/api/auto-editions/uploads/create?ticket=fixture',headers=headers,json=e.descriptor,timeout=5)
        response.raise_for_status();state=response.json();key=state['id']
        url=base+'/api/auto-editions/uploads/chunk?id='+key
        with e.path.open('rb') as source:
            first=source.read(CHUNK);second=source.read(CHUNK);last=source.read()
        h={**headers,'Content-Type':'application/octet-stream','X-SC-Chunk-Offset':'0','X-SC-Chunk-SHA256':e.descriptor['chunks'][0]}
        response=requests.post(url,headers=h,data=first,timeout=5);response.raise_for_status()
        assert response.json()['offset']==CHUNK
        parsed=urlsplit(base)
        raw=socket.create_connection((parsed.hostname,parsed.port),timeout=5)
        request=('POST /api/auto-editions/uploads/chunk?id='+key+' HTTP/1.1\r\nHost: '+parsed.netloc+
          '\r\nX-Sports-Cave-Preparation-Host: '+token+'\r\nContent-Type: application/octet-stream\r\nContent-Length: '+str(CHUNK)+
          '\r\nX-SC-Chunk-Offset: '+str(CHUNK)+'\r\nX-SC-Chunk-SHA256: '+e.descriptor['chunks'][1]+'\r\nConnection: close\r\n\r\n').encode()
        raw.sendall(request+second[:65536]);raw.shutdown(socket.SHUT_WR)
        try:raw.recv(4096)
        except (TimeoutError,ConnectionError):pass
        finally:raw.close()
        response=requests.post(base+'/api/auto-editions/uploads/status?id='+key,headers=headers,json={},timeout=5)
        response.raise_for_status();assert response.json()['offset']==CHUNK
        assert e.provider.sent==CHUNK
        for offset,payload,index in [(CHUNK,second,1),(2*CHUNK,last,2)]:
            h.update({'X-SC-Chunk-Offset':str(offset),'X-SC-Chunk-SHA256':e.descriptor['chunks'][index]})
            response=requests.post(url,headers=h,data=payload,timeout=5);response.raise_for_status()
        assert response.json()['offset']==e.descriptor['bytes']
        assert e.provider.sent==e.descriptor['bytes']
