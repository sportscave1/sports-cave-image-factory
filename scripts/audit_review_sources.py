"""Read-only bounded source identity/ICC audit for an already fixed review scope."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import auto_editions as ae
from auto_editions_colour_source import inspect_psd

if __name__=='__main__':
    out=Path('output/bulk-backlog-review')
    records={r['product_gid']:r for r in json.loads((out/'snapshot.json').read_text(encoding='utf-8'))['rows']}
    mirror=Path('C:/Users/hello/Sportscave Dropbox').resolve()
    output=out/'source-checks.json'
    results=json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    done={(r['product_gid'],r['hash']) for r in results}
    local=json.loads((out/'local-assets.json').read_text(encoding='utf-8'))
    def one(row):
        record=records[row['product_gid']];result=dict(product_gid=row['product_gid'],hash=record['preparation_hash'])
        try:
            if row['preparation_hash']!=record['preparation_hash'] or row['dropbox_file_id']!=record['source']['file_id']:
                raise ValueError('Preparation or source mapping changed since snapshot')
            path=Path(local[record['preparation_hash']]).parent/'input.psd' if record['preparation_hash'] in local else mirror/row['file_path'].lstrip('/')
            if not path.resolve().is_relative_to(mirror) and record['preparation_hash'] not in local:raise ValueError('Source path outside verified mirror')
            info=inspect_psd(path)
            result.update(source_hash_matches=ae.file_hash(path,dropbox=True)==record['source']['content_hash'],
                          profile_state=info['state'],profile=info['profile'],depth=info['depth'],mode=info['mode'],dimensions=[info['width'],info['height']])
        except Exception as error:result['unresolved']=str(error)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(one,r) for r in json.loads((out/'verified-source-paths.json').read_text(encoding='utf-8')) if (r['product_gid'],r['preparation_hash']) not in done]
        for task in as_completed(tasks):
            result=task.result();results.append(result);output.write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(len(results),result['product_gid'],result.get('profile_state',result.get('unresolved')),flush=True)
