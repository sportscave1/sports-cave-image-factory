"""Shared Postgres mappings, transactional audit, and conservative reviewed backfill."""
import hashlib
import json
import threading


class MappingUnavailable(RuntimeError):
    pass


class MappingConflict(ValueError):
    pass


def _record(row):
    return {**dict(row), 'verified': True, 'state': 'Linked', 'path': row['file_path']}


def preview(candidates, existing, product_ids):
    result = {'insert': [], 'preserved': [], 'conflicts': [], 'missing_products': []}
    owners = {r['dropbox_file_id']: pid for pid, r in existing.items()}
    for pid, row in sorted(candidates.items()):
        if not row.get('verified') or row.get('state') != 'Linked':
            continue
        fid = row['dropbox_file_id']
        if pid not in product_ids:
            result['missing_products'].append(pid)
        elif pid in existing:
            key = 'preserved' if existing[pid]['dropbox_file_id'] == fid else 'conflicts'
            result[key].append({'product_gid': pid, 'file_id': fid, 'existing': existing[pid]})
        elif fid in owners:
            result['conflicts'].append({'product_gid': pid, 'file_id': fid, 'assigned_product_gid': owners[fid]})
        else:
            owners[fid] = pid
            result['insert'].append({'product_gid': pid, 'file_id': fid, 'path': row['path'], 'namespace_path': row.get('namespace_path', '')})
    payload = json.dumps(result, sort_keys=True, default=str)
    result['preview_hash'] = hashlib.sha256(payload.encode()).hexdigest()
    return result


class PostgresMappings:
    def __init__(self, connect=None):
        self._connect = connect
        self._revision = None
        self._cache = {}
        self._lock = threading.RLock()

    def connect(self):
        if self._connect:
            return self._connect()
        import supabase_backend
        return supabase_backend.connect()

    @staticmethod
    def _all(cur):
        cur.execute('SELECT * FROM public.product_psd_mappings ORDER BY shopify_product_gid')
        return {r['shopify_product_gid']: _record(r) for r in cur.fetchall()}

    def read(self):
        """One indexed revision query per page; one batch read on revision changes."""
        def load(cur):
            with self._lock:
                cur.execute('SELECT COALESCE(max(id),0) AS revision FROM public.product_psd_mapping_audit')
                revision = cur.fetchone()['revision']
                if revision != self._revision:
                    mapping = self._all(cur)
                    self._cache, self._revision = mapping, revision
                return dict(self._cache)
        try:
            if self._connect:
                with self.connect() as conn, conn.cursor() as cur:
                    return load(cur)
            import supabase_backend
            return supabase_backend._run_read_operation('orders.psd_directory', load)[0]
        except Exception as error:
            raise MappingUnavailable('PSD directory is unavailable. Check database activation or retry.') from error

    @staticmethod
    def product(cur, pid):
        cur.execute("SELECT product_title,shopify_handle FROM edition_products WHERE COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id)=%s", (pid,))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise ValueError('Product identity is missing or ambiguous in Edition Ops.')
        return dict(rows[0])

    def get_product(self, pid):
        with self.connect() as conn, conn.cursor() as cur:
            return self.product(cur, pid)

    @staticmethod
    def _audit(cur, pid, action, actor, before, after):
        cur.execute('INSERT INTO public.product_psd_mapping_audit(shopify_product_gid,action,actor_id,before_state,after_state) VALUES(%s,%s,%s,%s::jsonb,%s::jsonb)',
                    (pid, action, actor, json.dumps(before, default=str) if before else None, json.dumps(after, default=str)))

    def attach(self, pid, metadata, actor, *, expected_file_id='', confirm_replace=False, confirm_mismatch=False):
        import psd_directory as psd
        import os_accounts
        if not os_accounts.can_attach_missing_psd(actor):
            raise PermissionError("You don't have permission to attach PSD files. Contact your administrator.")
        if not os_accounts.is_admin(actor) and (expected_file_id or confirm_replace):
            raise PermissionError('Only an administrator can replace an existing PSD mapping.')
        if not psd.product_id({'shopify_product_gid': pid}) or not psd.approved_file(metadata):
            raise ValueError('An approved main-folder PSD and valid product are required.')
        fid = metadata['id']
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('LOCK TABLE public.product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
            product = self.product(cur, pid)
            if psd.filename_key(metadata['name'][:-4]) not in psd.title_filename_keys(product['product_title']) and confirm_mismatch is not True:
                raise ValueError('Filename differs from the product title; explicit confirmation required.')
            existing = self._all(cur)
            before = existing.get(pid)
            # Check after the existing table lock: no VA overwrite, including stale/racing picks.
            if before is not None and not os_accounts.is_admin(actor):
                raise PermissionError('Only an administrator can replace an existing PSD mapping.')
            if (before or {}).get('dropbox_file_id', '') != expected_file_id:
                raise MappingConflict('Mapping changed while selecting. Reopen the picker.')
            if before and before['dropbox_file_id'] == fid and before.get('source') == 'manual':
                return before
            if before and confirm_replace is not True:
                raise MappingConflict('Replacing an existing mapping requires administrator confirmation.')
            if any(r['dropbox_file_id'] == fid and owner != pid for owner, r in existing.items()):
                raise MappingConflict('This PSD is already attached to another product.')
            actor_id = str(actor.get('id') or actor.get('username') or '')
            if not actor_id:
                raise PermissionError('An identified account is required.')
            cur.execute("INSERT INTO public.product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,namespace_path,source,actor_id) VALUES(%s,%s,%s,%s,'manual',%s) ON CONFLICT(shopify_product_gid) DO UPDATE SET dropbox_file_id=EXCLUDED.dropbox_file_id,file_path=EXCLUDED.file_path,namespace_path=EXCLUDED.namespace_path,source='manual',actor_id=EXCLUDED.actor_id,updated_at=now() RETURNING *",
                        (pid, fid, metadata.get('path_display') or metadata.get('path_lower'), metadata.get('namespace_path') or '', actor_id))
            after = _record(cur.fetchone())
            self._audit(cur, pid, 'replace' if before else 'attach', actor_id, before, after)
            # Add and its preparation checkpoint commit together. Older schemas
            # keep the existing mapping behavior during a rolling deployment.
            cur.execute("SELECT to_regclass('public.auto_edition_onboarding') AS name")
            if cur.fetchone()['name']:
                cur.execute("""INSERT INTO public.auto_edition_onboarding(product_gid,file_id,priority)
                    VALUES(%s,%s,2) ON CONFLICT(product_gid) DO UPDATE SET file_id=excluded.file_id,
                    source=NULL,preparation_hash=NULL,status='Awaiting preparation',reason='',attempts=0,priority=2,
                    lease_token=NULL,lease_until=NULL,updated_at=now()
                    WHERE auto_edition_onboarding.file_id<>excluded.file_id""",(pid,fid))
                cur.execute("""INSERT INTO public.auto_edition_onboarding_audit(product_gid,actor_id,event)
                    VALUES(%s,%s,'mapping_confirmed')""",(pid,actor_id))
        self._revision = None
        return after

    def backfill(self, candidates, *, execute=False, approval='', preview_hash=''):
        if execute and (not approval.strip() or not preview_hash):
            raise PermissionError('Separate owner approval and a reviewed preview hash are required.')
        with self.connect() as conn, conn.cursor() as cur:
            if execute:
                if not approval.strip() or not preview_hash:
                    raise PermissionError('Separate owner approval and a reviewed preview hash are required.')
                cur.execute('LOCK TABLE public.product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
            existing = self._all(cur)
            cur.execute("SELECT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id) AS pid,shopify_handle FROM edition_products")
            catalogue = cur.fetchall()
            identities = {}
            for product in catalogue:
                identities.setdefault(product['pid'], []).append(product)
            valid_ids = {pid for pid, products in identities.items() if len(products) == 1 and (not candidates.get(pid, {}).get('handle') or candidates[pid]['handle'] == products[0]['shopify_handle'])}
            report = preview(candidates, existing, valid_ids)
            if not execute:
                return report
            if report['preview_hash'] != preview_hash:
                raise MappingConflict('Preview changed; review a fresh preview before executing.')
            import psd_directory as psd
            for row in report['insert']:
                if not psd.approved_file({'.tag':'file','id':row['file_id'],'name':row['path'].rsplit('/',1)[-1],'path_display':row['path']}):
                    raise ValueError('Backfill contains an invalid approved-file identity.')
                cur.execute("INSERT INTO public.product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,namespace_path,source,actor_id) VALUES(%s,%s,%s,%s,'automatic',%s) ON CONFLICT DO NOTHING RETURNING *",
                            (row['product_gid'],row['file_id'],row['path'],row['namespace_path'],approval))
                after = cur.fetchone()
                if not after:
                    raise MappingConflict('Concurrent mapping conflict; transaction rolled back.')
                self._audit(cur,row['product_gid'],'automatic',approval,None,_record(after))
        self._revision = None
        return report


STORE = PostgresMappings()
