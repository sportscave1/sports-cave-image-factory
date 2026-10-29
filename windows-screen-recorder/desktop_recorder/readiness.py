"""Deterministic OFFLINE nonproduction preflight. Never grants external execution.

An independently reviewed approval binds the entire manifest; a self-authored
approval is only test data. Remote store type, file access/revisions and product
isolation still need supported live observations before native dispatch exists.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

from .contract import Invalid
from .followup_receipts import CHAT, DIGEST


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise Invalid('Missing or unexpected readiness fields.')


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise Invalid('Explicit bounded readiness value required.')
    return value


def check_file(path, digest):
    if not DIGEST.fullmatch(text(digest)):
        raise Invalid('Invalid SHA256.')
    path = Path(text(path))
    if not path.is_absolute() or not path.is_file() or not 0 < path.stat().st_size <= 50*1024*1024:
        raise Invalid('Missing or invalid bounded local file.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise Invalid('File changed or swapped after verification.')
    return str(path.resolve()).casefold()


def inspect(manifest, approval):
    exact(manifest, 'store destination target browser files prompt')
    exact(approval, 'manifest_sha256 evidence_id required_roles')
    text(approval['evidence_id'])
    if approval['manifest_sha256'] != fingerprint(manifest):
        raise Invalid('Manifest is not bound to the independently reviewed approval.')
    roles = approval['required_roles']
    if (not isinstance(roles, list) or len(roles) != 8
            or any(not isinstance(r, str) or not r.strip() for r in roles) or len(set(roles)) != 8):
        raise Invalid('Exactly eight explicitly approved roles required.')
    store = manifest['store']
    exact(store, 'id domain kind')
    text(store['id'])
    domain = text(store['domain'])
    if (store['kind'] != 'development' or not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com', domain)
            or store['id'].casefold() == 'sportscave-nb' or domain == 'sportscave-nb.myshopify.com'):
        raise Invalid('Only an explicitly approved development store is admissible; production refused.')
    destination = manifest['destination']
    exact(destination, 'namespace_id root test_only')
    text(destination['namespace_id'])
    root = text(destination['root'])
    if destination['test_only'] is not True or not re.fullmatch(r'/RecorderNonproduction/[A-Za-z0-9_-]+', root):
        raise Invalid('An isolated RecorderNonproduction destination is required.')
    target = manifest['target']
    exact(target, 'id store_id state isolated')
    text(target['id'])
    if target['store_id'] != store['id'] or target['state'] != 'DRAFT' or target['isolated'] is not True:
        raise Invalid('Explicit isolated draft target in the approved store required.')
    browser = manifest['browser']
    exact(browser, 'family profile extension_instance file_url_access conversation_url source_url mapping_url')
    if browser['family'] not in ('chrome', 'edge') or browser['file_url_access'] is not True:
        raise Invalid('Verified supported browser and file access required.')
    text(browser['profile']); text(browser['extension_instance'])
    if not CHAT.fullmatch(text(browser['conversation_url'])):
        raise Invalid('Exact intended project conversation required.')
    for key, page in [('source_url', 'product_uploads'), ('mapping_url', 'edition_ops')]:
        parsed = urlsplit(text(browser[key]))
        if (parsed.username or parsed.password or parsed.fragment or parsed.path != '/'
                or parsed.query != 'page='+page or parsed.scheme not in ('http', 'https')
                or not parsed.hostname or parsed.hostname == 'sports-cave-image-factory.onrender.com'
                or (parsed.scheme == 'http' and parsed.hostname != '127.0.0.1')):
            raise Invalid('Exact nonproduction Sports Cave page required.')
    source, mapping = (urlsplit(browser[k]) for k in ('source_url', 'mapping_url'))
    if (source.scheme, source.netloc) != (mapping.scheme, mapping.netloc):
        raise Invalid('Mapping destination changed origin.')
    files = manifest['files']
    if not isinstance(files, list) or len(files) != 8:
        raise Invalid('Eight verified files required.')
    identities, paths, destinations, hashes, found_roles = set(), set(), set(), set(), set()
    for entry in files:
        exact(entry, 'role id revision sha256 local_path destination_path')
        for key in ('role', 'id', 'revision', 'destination_path'):
            text(entry[key])
        if entry['revision'].casefold() in ('local-only', 'simulated', 'unknown', 'pending'):
            raise Invalid('Simulated or unresolved file revisions cannot pass readiness.')
        remote = PurePosixPath(entry['destination_path'])
        if ('\\' in entry['destination_path'] or '..' in remote.parts
                or str(remote) != entry['destination_path']
                or remote.parent != PurePosixPath(root)
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.webp', remote.name)):
            raise Invalid('File lies outside the exact test-only destination.')
        local = check_file(entry['local_path'], entry['sha256'])
        values = (entry['id'], local, str(remote).casefold(), entry['sha256'], entry['role'])
        for seen, value in zip((identities, paths, destinations, hashes, found_roles), values):
            if value in seen:
                raise Invalid('Ambiguous or duplicate file/role identity.')
            seen.add(value)
    if found_roles != set(roles):
        raise Invalid('File roles differ from the approved eight roles.')
    exact(manifest['prompt'], 'path sha256')
    check_file(manifest['prompt']['path'], manifest['prompt']['sha256'])
    return dict(local_contract_passed=True, external_ready=False, may_send=False,
                coverage='offline-contract-only', manifest_sha256=fingerprint(manifest),
                files_checked=8, pending=['Remote development-store identity',
                    'Remote file revisions/access and isolated draft', 'Fresh browser/profile/permission observation',
                    'Full prompt destination/effects review', 'Native follow-up and Windows acceptance'])


def load_document(path):
    if not 0 < path.stat().st_size <= 2*1024*1024:
        raise Invalid('Readiness document is empty or exceeds its bound.')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Invalid('Ambiguous duplicate JSON key.')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(load_document(args.manifest), load_document(args.approval))
    except (ValueError, OSError, Invalid) as error:
        print(json.dumps(dict(local_contract_passed=False, external_ready=False, may_send=False, error=str(error))))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
