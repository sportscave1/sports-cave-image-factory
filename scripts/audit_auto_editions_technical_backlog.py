"""Classify a read-only exported checkpoint snapshot. Never connects or enqueues."""
import argparse,csv,json,sys,time
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auto_editions_technical import backlog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=json.loads(args.snapshot.read_text(encoding='utf-8'))
    class Snapshot:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return self
        def execute(self,sql):pass
        def fetchall(self):return data
    start=time.perf_counter();result=backlog(Snapshot);elapsed=round((time.perf_counter()-start)*1000,2)
    titles={r['product_gid']:r.get('product_title','') for r in data}
    result=[dict(title=titles[r['product_gid']],**r) for r in result]
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'backlog.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (args.output/'backlog.csv').open('w',encoding='utf-8-sig',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    print(json.dumps(dict(total=len(result),counts=dict(Counter(r['group'] for r in result)),classification_ms=elapsed)))


if __name__=='__main__':main()
