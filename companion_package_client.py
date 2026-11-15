"""Restart-safe package client. No fallback after resumable negotiation."""
import json
from pathlib import Path
import time
from urllib.parse import urlencode
import requests
import auto_editions as ae
from companion_package_identity import describe,CHUNK
from companion_transfer import post_file


def upload(controller,path,grant,host_config,journal,*,correlation,stopped=lambda:False,on_trace=lambda t:None,
           poll_interval=5,verification_timeout=1800):
    path=Path(path);journal=Path(journal)
    descriptor=describe(path);identity=ae.fingerprint(descriptor)
    base=grant['base_url']
    prefix=grant.get('upload_path','/api/auto-editions/uploads/')
    if prefix not in ('/api/auto-editions/uploads/','/api/auto-editions/acceptance/'):
        raise ValueError('Unsupported upload route.')
    if host_config['base_url']!=base:raise ValueError('Preparation origin changed.')
    headers={'X-Sports-Cave-Preparation-Host':host_config['token'],'X-SC-Transfer-ID':correlation}

    def accept(result):
        import re
        if result.get('protocol')!=1 or result.get('sha256')!=descriptor['sha256'] or result.get('preparation_hash')!=descriptor['preparation_hash']:
            raise ValueError('Server upload session identity changed.')
        if (not re.fullmatch('[a-f0-9]{64}',str(result.get('id',''))) or result.get('bytes')!=descriptor['bytes']
            or result.get('state') not in ('Receiving','Queued','Complete','Blocked','Expired')
            or result.get('generation',descriptor['generation'])!=descriptor['generation']):
            raise ValueError('Server upload session binding changed.')
        offset=result.get('offset')
        if type(offset) is not int or not 0<=offset<=descriptor['bytes'] or offset!=descriptor['bytes'] and offset%CHUNK:
            raise ValueError('Server upload position is invalid.')
        if result['state'] in ('Queued','Complete') and offset!=descriptor['bytes']:
            raise ValueError('Server completion precedes durable package reception.')
        if (result.get('result') or {}).get('preparation_hash',descriptor['preparation_hash'])!=descriptor['preparation_hash']:
            raise ValueError('Server completed a different preparation.')
        return result

    def control(action,body=None,key=None):
        query={'id':key} if key else {'ticket':grant['ticket']}
        response=requests.post(base+prefix+action+'?'+urlencode(query),
            json={} if body is None else body,headers={**headers,'X-Sports-Cave-Transfer-Secret':grant['secret']},
            timeout=(20,90),allow_redirects=False)
        response.raise_for_status();result=accept(response.json())
        if key and result['id']!=key:raise ValueError('Server changed the retained upload session.')
        return result

    def save(state):
        # Never persist a provider session ID, transfer grant, host token or URL.
        from companion_atomic import atomic_json
        atomic_json(journal,dict(protocol=1,descriptor=identity,id=state['id'],confirmed_bytes=state['offset']))

    if journal.exists():
        if journal.stat().st_size>4096:raise ValueError('Bounded resumable journal required.')
        saved=json.loads(journal.read_text(encoding='utf-8'))
        if saved.get('protocol')!=1 or saved.get('descriptor')!=identity:raise ValueError('Retained resumable package fingerprint changed.')
        state=control('status',key=saved['id'])
        if state['offset']<saved['confirmed_bytes']:raise ValueError('Server lost durably confirmed progress; replay refused.')
        save(state)
    else:
        state=control('create',descriptor);save(state)
    with controller.slot(descriptor['bytes'],correlation,stopped,resumable=True,
                         verification_only=state['offset']==descriptor['bytes']) as trace:
        trace.update(server_received_bytes=state['offset'],confirmed_bytes=state['offset'],resumed_bytes=state['offset'],progress_bytes=state['offset'],transfer_seconds=0.)
        while state['state']=='Receiving' and state['offset']<descriptor['bytes']:
            waited=controller.chunk_boundary(trace,stopped)
            if waited:
                confirmed=state['offset']
                state=control('status',key=state['id'])
                if state['offset']<confirmed:raise ValueError('Server lost durably confirmed progress after pause; replay refused.')
                trace['confirmed_bytes']=state['offset'];trace['server_received_bytes']=state['offset'];trace['progress_bytes']=state['offset']
                save(state)
                if state['state']!='Receiving' or state['offset']==descriptor['bytes']:break
            offset=state['offset'];length=min(CHUNK,descriptor['bytes']-offset)
            trace['state']='Uploading'
            response,_=post_file(controller,base+prefix+'chunk?'+urlencode({'id':state['id']}),path,
                {**headers,'Content-Type':'application/octet-stream','X-SC-Chunk-Offset':str(offset),
                 'X-SC-Chunk-SHA256':descriptor['chunks'][offset//CHUNK]},
                correlation=correlation,stopped=stopped,on_trace=on_trace,offset=offset,length=length,_parent=trace)
            response.raise_for_status()
            # The successful response follows SQL commit. Lost ACKs recover by
            # querying status on restart; no extra status RTT for every chunk.
            state=accept(response.json())
            if state['id']!=json.loads(journal.read_text())['id']:raise ValueError('Chunk acknowledgement changed the upload session.')
            if state['offset']<offset+length and state['state']=='Receiving':raise ValueError('Server did not durably acknowledge the chunk.')
            trace['confirmed_bytes']=state['offset'];trace['server_received_bytes']=state['offset'];trace['progress_bytes']=state['offset']
            save(state)
        trace['state']='Uploaded, verifying';verification=time.monotonic()
        if state['state']=='Receiving':state=control('finalize',key=state['id']);save(state)
        while state['state'] in ('Queued','Complete'):
            result=state.get('result') or {}
            if state['state']=='Complete' and result.get('preparation_hash'):
                # Imported/verified are distinct. A non-Cloud-Ready durable
                # result remains under the existing technical worker's gates.
                trace['state']='Cloud Ready' if result.get('status')=='Cloud Ready' else 'Uploaded, verifying'
                trace['verification_seconds']=time.monotonic()-verification
                on_trace(trace)
                return result
            if stopped():raise InterruptedError('Stopped with durable upload progress retained.')
            if time.monotonic()-verification>verification_timeout:raise requests.ReadTimeout('Durable server verification still pending.')
            time.sleep(poll_interval) # Worker thread only; heartbeat remains independent.
            state=control('status',key=state['id'])
            trace['verification_seconds']=time.monotonic()-verification
        raise ValueError('Durable upload blocked or expired; package retained for review.')
