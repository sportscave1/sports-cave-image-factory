"""Read a fixed owner-authorised snapshot and mirrored assets; never write live data.

Outputs diagnostic views only. An unprofiled diagnostic view is not approval proof.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
import auto_editions as ae
import auto_editions_bulk as bulk


def audit(snapshot, mirror, output):
    output.mkdir(parents=True, exist_ok=True)
    results=json.loads((output/'asset-checks.json').read_text(encoding='utf-8')) if (output/'asset-checks.json').exists() else []
    completed={r['hash'] for r in results}
    def one(record):
        start=time.perf_counter()
        digest=record['preparation_hash']; record={**record,'hash':digest}
        m=record['manifest']; root=mirror/digest
        result=dict(product_gid=record['product_gid'],title=record['product_title'],hash=digest,
                    checks={},errors=[],visual_review='Pending',approved=False)
        try:
            bulk.evidence(record); result['checks']['manifest_proofs_receipts_geometry']='Passed'
        except Exception as error:result['errors'].append(str(error))
        asset_errors=[]; profiles={}; valid=0
        try:
            with Image.open(root/m['master']['name']) as master_header:
                master_has_icc=bool(master_header.info.get('icc_profile'))
        except Exception as error:
            result['errors'].append(str(error));result['visual_review']='Unavailable';result['checks']['existing_master_validator']='Asset unavailable';return result
        assets=[m['master'],*m['patches'].values()] if master_has_icc else [m['master'],m['patches']['1'],m['patches'][str(m['edition_total'])]]
        result['validation_stopped_at_missing_master_icc']=not master_has_icc
        for asset in assets:
            try:
                path=ae.asset_path(root,asset)
                receipt=next(r for r in record['receipts']['assets'] if r['name']==asset['name'])
                if path.stat().st_size!=receipt['bytes']:raise ValueError('Receipt size differs')
                region=m['number_region'];expected=m['dimensions'] if asset==m['master'] else [region[2]-region[0],region[3]-region[1]]
                with Image.open(path) as image:
                    if image.format!='PNG' or image.mode!='RGB' or list(image.size)!=expected:raise ValueError('Geometry or mode differs')
                    profiles[asset['name']]=len(image.info.get('icc_profile',b''))
                valid+=1
            except Exception as error:asset_errors.append(dict(name=asset['name'],error=str(error)))
        result['checks'].update(verified_asset_hashes_sizes_geometry=valid,total_assets=1+len(m['patches']),asset_errors=asset_errors,embedded_icc_bytes=profiles)
        try:
            bulk.inspect_asset(root,m['master'],m['dimensions'],lambda *args:None,digest,record['receipts'],(m.get('colour_evidence') or {}).get('icc_sha256'))
            result['checks']['existing_master_validator']='Passed'
        except Exception as error:
            result['checks']['existing_master_validator']=str(error);result['errors'].append(str(error))
        try:
            # Exact hash-verified composition, without assigning or converting colour.
            # Labelled diagnostic because missing ICC prevents validated review output.
            with Image.open(root/m['master']['name']) as source:
                image=source.copy()
            with Image.open(root/m['patches']['1']['name']) as patch:image.paste(patch,m['number_region'][:2])
            folder=output/digest;folder.mkdir(exist_ok=True)
            image.thumbnail((1600,1600));image.save(folder/'diagnostic-detail.png')
            with Image.open(root/m['master']['name']) as source:
                plaque=source.crop(tuple(m['plaque_bounds']))
            region=m['number_region'];p=m['plaque_bounds']
            with Image.open(root/m['patches']['1']['name']) as patch:plaque.paste(patch,(region[0]-p[0],region[1]-p[1]))
            plaque.thumbnail((1600,800));plaque.save(folder/'diagnostic-plaque.png')
            result['diagnostic_detail']=str(folder/'diagnostic-detail.png');result['diagnostic_plaque']=str(folder/'diagnostic-plaque.png')
        except Exception as error:result['errors'].append('Diagnostic composition unavailable: '+str(error))
        result['elapsed_seconds']=round(time.perf_counter()-start,3)
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks=[pool.submit(one,r) for r in snapshot['rows'] if r['preparation_hash'] not in completed]
        for task in as_completed(tasks):
            result=task.result();results.append(result)
            (output/'asset-checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(len(results),result['product_gid'],result['checks']['existing_master_validator'],flush=True)
    return results


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--mirror',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();audit(json.loads(args.snapshot.read_text(encoding='utf-8')),args.mirror,args.output)
