"""GET/SELECT-only audit; run where existing secured Meta credentials are available.

Does not reconcile by writing, clear errors, reset jobs, or create any resource.
Missing IDs and legacy generic failures require an operator's evidence review.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def audit(identity):
    from meta_posting_service import SupabasePostingStore
    from meta_ads_client import MetaPostingClient
    from meta_posting_recovery import requires_reconciliation, verify_resume_objects
    row = SupabasePostingStore().get(identity)
    if not row:
        raise ValueError('Submission not found')
    client = MetaPostingClient()
    checked = verify_resume_objects(client, row)
    result = {'submission_id': str(row['submission_id']), 'ledger_status': row['status'],
              'requires_reconciliation': requires_reconciliation(row), 'objects': {}, 'ads': []}
    for kind, obj in checked.items():
        result['objects'][kind] = {k: obj.get(k) for k in ('id','account_id','campaign_id','configured_status','status')}
    for saved in row.get('ad_results') or []:
        item = {'index': saved.get('index'), 'ad_id': saved.get('meta_ad_id'),
                'page_photo_id': saved.get('meta_page_photo_id'),
                'instant_experience_id': saved.get('meta_instant_experience_id')}
        if saved.get('meta_image_hash'):
            image = client.ad_image_details(saved['meta_image_hash'])
            item['image_hash_verified'] = image.get('hash') == saved['meta_image_hash']
        if item['instant_experience_id']:
            canvas = client.instant_experience(item['instant_experience_id'])
            item['instant_experience_found'] = str(canvas.get('id')) == item['instant_experience_id']
        if item['ad_id']:
            ad = client.ad(item['ad_id'])
            item['configured_status'] = ad.get('configured_status')
            item['adset_matches'] = str(ad.get('adset_id')) == str(row.get('adset_id'))
        result['ads'].append(item)
    result['note'] = 'Read-only evidence only. Missing IDs do not prove objects were never created. Do not reset or replay an unknown operation.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('submission_id')
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.submission_id), indent=2))
    except Exception as error:
        from meta_posting_recovery import diagnostic
        print(diagnostic(error, 'read_only_audit', args.submission_id), file=sys.stderr)
        raise SystemExit(1) from None
