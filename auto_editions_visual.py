"""Exact owner-reference visual approval. Disabled until separately released.

Colour approval alone is never visual authority. Storefront comparison is only a
veto/corroboration after exact source/reference/policy binding, never sole proof.
"""
from datetime import datetime,timezone,timedelta
import json,math,os,re,tempfile
from pathlib import Path
from functools import lru_cache
from PIL import Image,ImageChops,ImageStat
import auto_editions as ae
import auto_editions_quality as quality

POLICY='auto-editions-visual-v1'
POLICIES=Path(__file__).parent/'data/auto_editions_visual_policies.json'
def enabled():return os.getenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED','').lower()=='true'
def policies():
    stat=POLICIES.stat()
    return _policies(str(POLICIES),stat.st_mtime_ns,stat.st_size)
@lru_cache(maxsize=1)
def _policies(path,mtime,size):
    rows=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(rows,list):raise ValueError('Visual policy list required.')
    return rows
def sha(value):return bool(re.fullmatch('[a-f0-9]{64}',str(value or '')))
def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))

def policy_for(record,records):
    return _policy_for(record,records,ae.fingerprint(record['manifest']))

def _policy_for(record,records,digest):
    m=record['manifest']
    matches=[p for p in records if p.get('preparation_hash')==digest and p.get('source')==m['source'] and not p.get('revoked')]
    if len(matches)!=1:return None
    p=matches[0]
    try:
        if (p['policy']!=POLICY or p['owner_approved'] is not True or p['download_scope']!='TEST_ONLY'
                or not isinstance(p['id'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',p['id'])
                or any(not isinstance(p[k],str) or not p[k].strip() for k in ('actor_id','reference_approval_evidence'))
                or stamp(p['approved_at']).tzinfo is None or stamp(p['approved_at'])>datetime.now(timezone.utc)
                or p['output']['dimensions']!=m['dimensions'] or not sha(p['output']['icc_sha256'])):return None
        refs=p['references'];expected={'original.png'}|{f'reference-{n}.png' for n in {1,m['edition_total']}}
        if set(refs)!=expected:return None
        for name,r in refs.items():
            if not sha(r['sha256']) or any(not isinstance(r[k],str) or not r[k].strip() for k in ('file_id','revision')):return None
        proofs=record.get('proofs',[])
        if not any(x.get('original_sha256')==refs['original.png']['sha256'] and x.get('outside_number_exact') is True and x.get('preparation_hash')==digest for x in proofs):return None
        for n in {1,m['edition_total']}:
            if not any(x.get('number')==n and x.get('reference_sha256')==refs[f'reference-{n}.png']['sha256'] and x.get('pixel_exact') is True and x.get('preparation_hash')==digest for x in proofs):return None
        colour=m.get('colour_evidence')
        if colour:
            if colour.get('pixels_converted') is not False or colour.get('icc_sha256')!=p['output']['icc_sha256']:return None
            if colour.get('policy'):
                from auto_editions_colour_policy import resolve
                _,active=resolve(m['source'])
                if active!=colour['policy']:return None
        s=p['shopify']
        if (s['product_gid']!=m['source']['product_gid'] or not s['media_id'] or not sha(s['sha256'])
                or not s['product_revision'] or s['owner_reviewed_relationship'] is not True
                or type(s['maximum_mean_error']) not in (int,float) or not 0<=s['maximum_mean_error']<=0.08):return None
        ae.bounds(s['reference_region'],m['dimensions'])
        if len(s['artwork_quad'])!=8 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in s['artwork_quad']):return None
        q=list(zip(s['artwork_quad'][::2],s['artwork_quad'][1::2]))
        crosses=[(q[(i+1)%4][0]-q[i][0])*(q[(i+2)%4][1]-q[(i+1)%4][1])-(q[(i+1)%4][1]-q[i][1])*(q[(i+2)%4][0]-q[(i+1)%4][0]) for i in range(4)]
        if not (all(x>0 for x in crosses) or all(x<0 for x in crosses)):return None
        x0,y0,x1,y1=s['reference_region']
        if (x1-x0)*(y1-y0)<m['dimensions'][0]*m['dimensions'][1]*0.25:return None
        return p
    except (KeyError,TypeError,ValueError,AttributeError):return None

def current(approval,manifest,records=None,*,now=None):
    return current_identity(approval,ae.fingerprint(manifest),manifest,records,now=now)

def current_identity(approval,digest,summary,records=None,*,now=None):
    """Cheap listing fence against the immutable stored manifest identity.

    Listings select only source/dimensions/total, not hundreds of patch hashes.
    Generation still validates the complete manifest through current().
    """
    if not enabled() or not isinstance(approval,dict) or approval.get('method')!=POLICY:return False
    check=approval.get('assessment',{});now=now or datetime.now(timezone.utc)
    if not isinstance(check,dict):return False
    try:
        p=_policy_for(dict(manifest=summary,proofs=check.get('proofs',[])),policies() if records is None else records,digest)
        return bool(p and approval.get('actor_id')=='automatic:'+p['id'] and approval.get('test_only') is True
            and approval.get('visual_approved') is not True and approval.get('pixel_exact') is True
            and approval.get('preparation_hash')==digest and check['status']=='Auto Approved' and check.get('policy')==POLICY
            and approval.get('assessment_hash')==ae.fingerprint(check)
            and check['source']==summary['source'] and check['policy_hash']==ae.fingerprint(p)
            and stamp(check['checked_at'])<=now<stamp(check['expires_at'])<=stamp(check['checked_at'])+timedelta(hours=24)
            and check['evidence']['receipts_verified']==summary['edition_total']+1
            and check['evidence']['reference_comparison'] is True and check['evidence']['shopify_identity'] is True
            and check['evidence']['reference_hashes']=={n:r['sha256'] for n,r in p['references'].items()}
            and check['evidence']['shopify_media_id']==p['shopify']['media_id']
            and check['evidence']['print_ready'] is False and check['evidence']['fulfilment_authorized'] is False)
    except (KeyError,TypeError,ValueError):return False

def assess(record,mapping,checkpoint,source,metadata,fetch,reference_fetch,shopify,records):
    m=record['manifest'];p=policy_for(record,records)
    if not p:return quality.result('Needs Review','Visual policy awaiting approval: exact trusted reference evidence is insufficient.',m)
    def compare(root):
        for name,r in p['references'].items():
            destination=root/name;reference_fetch(r,destination)
            if ae.file_hash(destination)!=r['sha256']:raise quality.VisualEvidenceReview('Approved artwork reference bytes changed; review required.')
        # Recompute independent lossless comparisons, not just stored booleans.
        try:
            ae.compare_original_outside_number(m,root,1,root/'original.png')
            for n in {1,m['edition_total']}:ae.compare_reference(m,root,n,root/f'reference-{n}.png')
        except ValueError as error:
            raise quality.VisualEvidenceReview('Prepared artwork differs from the approved original or numbered reference.') from error
        s=p['shopify'];live=shopify(s,root/'shopify-image')
        if (live.get('product_gid')!=s['product_gid'] or live.get('product_revision')!=s['product_revision']
                or live.get('media_id')!=s['media_id'] or ae.file_hash(root/'shopify-image')!=s['sha256']):
            raise quality.VisualEvidenceReview('Live Shopify product revision, media identity or reviewed image bytes changed.')
        with Image.open(root/'shopify-image') as mockup,Image.open(root/'original.png') as original:
            if mockup.width*mockup.height>ae.WORKER_MAX_PIXELS:raise ValueError('Storefront comparison exceeds bounds.')
            q=s['artwork_quad']
            if any(q[i]> (mockup.width if i%2==0 else mockup.height) for i in range(8)):raise ValueError('Reviewed mockup coordinates differ.')
            points=list(zip(q[::2],q[1::2]));area=abs(sum(points[i][0]*points[(i+1)%4][1]-points[(i+1)%4][0]*points[i][1] for i in range(4)))/2
            if area<mockup.width*mockup.height*0.05:raise quality.VisualEvidenceReview('Storefront artwork comparison has insufficient visible coverage.')
            with mockup.convert('RGB') as rgb,original.crop(s['reference_region']) as crop:
                with rgb.transform((128,128),Image.Transform.QUAD,q,Image.Resampling.BICUBIC) as aligned,crop.resize((128,128),Image.Resampling.BICUBIC) as trusted:
                    with ImageChops.difference(aligned,trusted) as diff:error=sum(ImageStat.Stat(diff).mean)/3/255
            if error>s['maximum_mean_error']:raise quality.VisualEvidenceReview('Storefront artwork comparison is ambiguous or different.')
        return dict(reference_comparison=True,shopify_identity=True,shopify_mean_error=round(error,6),
                    reference_hashes={n:r['sha256'] for n,r in p['references'].items()},shopify_media_id=s['media_id'])
    try:check=quality.assess(record,mapping,checkpoint,source,metadata,fetch,[],visual=p,compare=compare)
    except Exception:check=quality.result('Failed','Visual reference or Shopify identity verification failed.',m)
    now=datetime.now(timezone.utc)
    check.update(policy=POLICY,policy_hash=ae.fingerprint(p),checked_at=now.isoformat(),expires_at=(now+timedelta(hours=24)).isoformat(),proofs=record.get('proofs',[]))
    # Keep precise safe reasons for ambiguous references; never promote a failure.
    if check['status']=='Auto Approved':check['reason']='Auto Approved: exact source, approved references and cloud assets verified. TEST downloads only; supplier certification remains separate.'
    return check

def approval(check,manifest,records=None):
    p=policy_for(dict(manifest=manifest,proofs=check.get('proofs',[])),policies() if records is None else records)
    value=dict(method=POLICY,actor_id='automatic:'+p['id'] if p else '',preparation_hash=ae.fingerprint(manifest),
               pixel_exact=True,test_only=True,assessment=check,assessment_hash=ae.fingerprint(check))
    if not current(value,manifest,records):raise ValueError('Current automatic visual evidence required.')
    return value
