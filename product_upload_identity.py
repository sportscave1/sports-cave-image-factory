"""Upload identity shared by prompt generation, catalogue lookup and mapping."""
from copy import deepcopy
import uuid


def operation(row):
    data = row['data']
    source = data.get('source')
    if not source or not source.get('id') or not source.get('rev') or not source.get('content_hash'):
        raise ValueError('Select a verified Dropbox PSD before mapping.')
    saved = data.get('upload_operation')
    if not saved:
        saved = dict(id=str(uuid.UUID(str(row['id']))), provider='dropbox', source=deepcopy(source))
        data['upload_operation'] = saved
    if any(saved['source'].get(k) != source.get(k) for k in ('id', 'rev', 'content_hash')):
        raise ValueError('This upload source has changed. Reopen the original upload or start a new one.')
    if saved.get('id') != str(row['id']) or saved.get('provider') != 'dropbox':
        raise ValueError('The saved upload operation identity is inconsistent. Review the original upload.')
    if saved.get('product_id') and data.get('product_gid') and saved['product_id'] != data['product_gid']:
        raise ValueError('The saved upload has conflicting Shopify product identities. Review its mapping.')
    return saved


def tag(key):
    return 'sc-upload-' + uuid.UUID(str(key)).hex


def correlation_prompt(row):
    op = operation(row)
    op['correlation_expected'] = True
    return f'''UPLOAD OPERATION CORRELATION — REQUIRED
Keep the exact product tag {tag(op['id'])} on the product created or explicitly updated by this operation.
This is a non-secret correlation label, not a credential. Add it to the product's existing tags; never replace unrelated tags.
Before creating or retrying, search Shopify for this exact tag (including drafts). If exactly one product carries it, resume that product by its stable ID; do not create another. If more than one carries it, stop and report the conflict.
The Shopify creation connector supports tags. Include this tag in the initial create call, not a later optional step. In Update Existing mode attach it only to the explicitly confirmed existing product.
Also add sc-edition-limit-N, replacing N with the edition limit confirmed from the supplied product/artwork or user. Do not guess a limit. Do not change existing edition counters or history.
Read the product back and verify the correlation tag. Report its stable ID and handle. Preserve the selected Draft/Live/Update publication instructions.
After completion, return to Product Uploads and click MAP. No product-name paste is required. If the connector cannot persist the tag, report that limitation and the stable product ID for the exceptional product selector.
END UPLOAD OPERATION CORRELATION

'''
