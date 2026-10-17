"""Disposable loopback SQL client for independent-process cache tests only."""
import json
from pathlib import Path
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).parents[1]))
from auto_editions_review_thumbnails import ReviewBuildStore
from auto_editions_bulk import ReviewCache


class Connection:
    def __init__(self,url):
        if not url.startswith('http://127.0.0.1:'):raise ValueError('Loopback tests only.')
        self.url=url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def execute(self,sql,args=()):
        parts=sql.split('%s');sql=parts[0]+''.join('$'+str(i)+p for i,p in enumerate(parts[1:],1))
        req=urllib.request.Request(self.url,data=json.dumps(dict(sql=sql,args=args)).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as response:self.rows=json.load(response)['rows']
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


if __name__=='__main__':
    import shutil
    url,export,root,start,transfers=sys.argv[1:]
    record=json.loads(Path(export).read_text());store=ReviewBuildStore(lambda:Connection(url))
    print('ready',flush=True)
    deadline=time.monotonic()+15
    while not Path(start).exists():
        if time.monotonic()>deadline:raise TimeoutError('Isolated test start barrier failed.')
        time.sleep(.01)
    def fetch(digest,asset,target):
        with Path(transfers).open('a') as log:log.write(asset['name']+'\n')
        time.sleep(.1);shutil.copyfile(Path(root)/asset['name'],target)
    cache=ReviewCache();result=cache.get(record,fetch,store=store)
    print(json.dumps(dict(built=result is not None)),flush=True)
