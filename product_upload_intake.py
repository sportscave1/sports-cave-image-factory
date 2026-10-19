"""Durable, bounded PSD intake. No Shopify creation, Photoshop or order work here."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import struct
import uuid

CHUNK = 4 * 1024 * 1024  # Stable Dropbox hash blocks and legacy resume offsets.
TRANSPORT_CHUNK = 2 * CHUNK  # Existing adapter supports 8 MiB ordered appends.
MAX_BYTES = 1024 ** 3
MODES = {'DRAFT': 'Upload to Draft', 'LIVE': 'Upload to Live', 'UPDATE': 'Update Existing'}


def mode(value):
    if value not in MODES:
        raise ValueError('Choose Draft, Live or Update Existing.')
    return value


def inspect_chunk(state, data, offset, size):
    """Incremental PSD section framing; skip payloads, never decode a full image.

    This is basic validation, NOT proof of editable numbering, fonts or colour.
    Native inspection remains authoritative. State is small and JSON serialisable.
    """
    state = dict(state or {'stage': 0, 'at': 0, 'carry': ''})
    view = memoryview(data)
    while state['stage'] < 5 and state['at'] < offset + len(view):
        start = state['at'] - offset
        if start < 0:
            raise ValueError('PSD validation offset changed; resume the same upload.')
        need = (26 if state['stage'] == 0 else 2 if state['stage'] == 4 else 4)
        part = bytes.fromhex(state['carry'])
        take = min(need - len(part), len(view) - start)
        part += view[start:start + take].tobytes()
        state['at'] += take
        if len(part) < need:
            state['carry'] = part.hex()
            break
        state['carry'] = ''
        stage = state['stage']
        if stage == 0:
            sig, version, reserved, channels, height, width, depth, colour = struct.unpack('>4sH6sHIIHH', part)
            if sig != b'8BPS' or version != 1 or reserved != b'\0' * 6:
                raise ValueError('This is not a supported Photoshop PSD. Export a layered PSD, not PSB or an image renamed .psd.')
            if not 3 <= channels <= 56 or not 1 <= width <= 30000 or not 1 <= height <= 30000:
                raise ValueError('PSD channels or canvas dimensions are unsupported.')
            if colour != 3 or depth != 8:
                raise ValueError('The current Companion requires an RGB, 8-bit layered PSD. Preserve your original and export a compatible copy.')
            from auto_editions import WORKER_MAX_PIXELS
            if width * height > WORKER_MAX_PIXELS:
                raise ValueError('PSD canvas exceeds the supported Companion pixel budget.')
            state['document'] = dict(width=width, height=height, depth=depth, colour='RGB', channels=channels)
        elif stage < 4:
            length = int.from_bytes(part, 'big')
            if stage == 3 and length < 8:
                raise ValueError('A layered PSD is required; the layer section is missing.')
            if state['at'] + length > size - 2:
                raise ValueError('PSD section extends beyond the saved file. Re-export the complete PSD.')
            state['at'] += length
        elif int.from_bytes(part, 'big') not in (0, 1, 2, 3):
            raise ValueError('Unsupported PSD image compression.')
        state['stage'] += 1
    return state


class Intakes:
    def __init__(self, connect):
        self.connect = connect

    @contextmanager
    def locked(self, key, actor, *, provider_io=False):
        with self.connect() as conn, conn.cursor() as cur:
            if provider_io:
                cur.execute("SET LOCAL idle_in_transaction_session_timeout = '5min'", ())
            cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s AND actor_id=%s FOR UPDATE', (str(uuid.UUID(key)), str(actor)))
            row = cur.fetchone()
            if not row:
                raise ValueError('This saved upload is unavailable to this account.')
            row = dict(row)
            before = (row['mode'], json.dumps(row['data'], sort_keys=True))
            yield row, cur
            if before != (row['mode'], json.dumps(row['data'], sort_keys=True)):
                cur.execute('UPDATE product_upload_intakes SET mode=%s,data=%s::jsonb,updated_at=now() WHERE id=%s',
                            (row['mode'], json.dumps(row['data']), row['id']))

    def read(self, key, actor):
        with self.connect() as conn, conn.cursor() as cur:
            if key:
                cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s AND actor_id=%s', (str(uuid.UUID(key)), str(actor)))
            else:
                cur.execute('SELECT * FROM product_upload_intakes WHERE actor_id=%s ORDER BY created_at DESC LIMIT 1', (str(actor),))
            row = cur.fetchone()
            return dict(row) if row else None

    def create(self, key, actor, selected, name, size, provider, content_hash):
        key = str(uuid.UUID(key)); mode(selected)
        if not isinstance(name, str) or not name.lower().endswith('.psd') or len(name) > 255 or any(ord(c) < 32 for c in name):
            raise ValueError('Select a PSD file with a valid filename.')
        if type(size) is not int or not 40 <= size <= MAX_BYTES:
            raise ValueError('Supported PSD size is 40 bytes to 1 GiB.')
        if not re.fullmatch('[a-f0-9]{64}', str(content_hash)):
            raise ValueError('The complete file identity is required before upload.')
        with self.connect() as conn, conn.cursor() as cur:
            # A retry of start must recover the same provider session and record.
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('product-upload:' + key,))
            cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s', (key,))
            old = cur.fetchone()
            if old:
                if old['actor_id'] != str(actor) or old['data']['name'] != name or old['data']['size'] != size or old['data']['content_hash'] != content_hash:
                    raise ValueError('Upload identity already belongs to another file.')
                return dict(old)
            data = dict(name=name, size=size, content_hash=content_hash, offset=0, blocks=[], structure={}, state='Uploading PSD',
                        session=provider.start(), destination=provider.destination(key),
                        expires=(datetime.now(timezone.utc) + timedelta(days=6)).isoformat(), copied=False, workflow_version=2)
            cur.execute('INSERT INTO product_upload_intakes(id,actor_id,mode,data) VALUES(%s,%s,%s,%s::jsonb) RETURNING *',
                        (key, str(actor), selected, json.dumps(data)))
            return dict(cur.fetchone())

    def chunk(self, key, actor, offset, content, provider):
        if type(offset) is not int or offset < 0 or offset % CHUNK:
            raise ValueError('Invalid upload offset.')
        with self.locked(key, actor, provider_io=True) as (row, cur):
            d = row['data']
            length = len(content)
            # HTTP batches may combine hash blocks; durable hashes/offsets stay compatible
            # with existing 4 MiB sessions and old browser clients. Only the final batch
            # may end partway through a hash block.
            if not 0 < length <= TRANSPORT_CHUNK or offset + length > d['size'] or (offset + length < d['size'] and length % CHUNK):
                raise ValueError('A complete bounded upload chunk is required.')
            view = memoryview(content)
            digests = [hashlib.sha256(view[at:at + CHUNK]).hexdigest() for at in range(0, length, CHUNK)]
            if offset < d['offset']:
                first = offset // CHUNK
                if offset + length > d['offset'] or digests != d['blocks'][first:first + len(digests)]:
                    raise ValueError('Retry bytes differ from the saved PSD. Select the same file or start a new upload.')
                return row
            if d.get('source') or offset != d['offset']:
                raise ValueError('Upload position changed. Refresh and resume from the saved offset.')
            if datetime.fromisoformat(d['expires']) <= datetime.now(timezone.utc):
                raise ValueError('The interrupted transfer expired. Choose the PSD again to start a new saved upload.')
            structure = inspect_chunk(d['structure'], content, offset, d['size'])
            try:
                provider.append(d['session'], offset, content)
            except Exception as error:
                # Provider accepted bytes but acknowledgement/DB commit was lost.
                # Final content hash independently proves those bytes match.
                confirmed = getattr(error, 'correct_offset', None)
                # An older 8 MiB append may have succeeded before its DB commit
                # or ACK was lost. Recover it using stable 4 MiB checkpoints;
                # final storage content_hash still independently verifies bytes.
                if (type(confirmed) is not int or not offset + length <= confirmed <= min(d['size'], offset + TRANSPORT_CHUNK)
                        or (confirmed != d['size'] and confirmed % CHUNK)):
                    raise
            d['blocks'].extend(digests); d['offset'] += length; d['structure'] = structure
            if d['offset'] == d['size']:
                d['state'] = 'Checking design'
            return row

    def finish(self, key, actor, provider):
        with self.locked(key, actor) as (row, cur):
            d = row['data']
            if d.get('source'):
                return row
            if d['offset'] != d['size'] or d['structure'].get('stage') != 5:
                raise ValueError('PSD transfer or structure is incomplete. Resume the upload.')
            expected = hashlib.sha256(b''.join(bytes.fromhex(h) for h in d['blocks'])).hexdigest()
            if expected != d['content_hash']:
                raise ValueError('Uploaded bytes do not match the selected file. Start a new upload with the original PSD.')
            # Deterministic destination recovers a finish whose response was lost.
            meta = provider.metadata_if_present(d['destination'])
            if meta is None:
                provider.finish(d['session'], d['size'], d['destination'])
                meta = provider.metadata_if_present(d['destination'])
            if not meta or meta.get('size') != d['size'] or meta.get('content_hash') != expected:
                raise ValueError('Saved PSD verification failed. The file has not been accepted for preparation.')
            import auto_editions as ae
            ae.source_identity('gid://shopify/Product/1', meta)  # Validate provider identity, not a provisional mapping.
            d.update(source=meta, state='Uploaded', basic_validated=True, copied=False)
            d.pop('session', None)
            return row

    def change_mode(self, key, actor, selected):
        with self.locked(key, actor) as (row, cur):
            mode(selected)
            if row['mode'] != selected:
                if row['data'].get('product_gid'):
                    raise ValueError('This PSD is already linked. Start a new upload for another action.')
                row['mode'] = selected
                row['data'].update(copied=False, lookup='', choices=[])
            return row

    def copied(self, key, actor, selected, source_version=None):
        with self.locked(key, actor) as (row, cur):
            if row['mode'] != selected or not row['data'].get('basic_validated'):
                raise ValueError('Upload or action changed. Copy the current prompt again.')
            if row['data'].get('workflow_version') in (2,3) and not row['data'].get('mockups_exported'):
                raise ValueError('Save or download the completed image package before the Shopify handoff.')
            if source_version is not None:
                from product_upload_source import current_source
                current_source(row, source_version)
            row['data']['copied'] = True
            return row


def public(row):
    if not row:
        return None
    d = row['data']
    # No provider session, tokens, storage path or raw worker errors in the UI.
    result = dict(id=str(row['id']), mode=row['mode'], transport_chunk_bytes=TRANSPORT_CHUNK, relay_resume=True, **{k:d.get(k) for k in (
        'name','size','offset','state','basic_validated','copied','lookup','choices','product_title',
        'preparation_hash','reason','preview_url','product_url','companion_connected','shopify_completion',
        'selected_at')})
    if d.get('artwork_progress'):result['artwork_progress']=d['artwork_progress']
    if d.get('mockups_exported'):
        result['saved_package_version']=((d.get('upload_operation') or {}).get('output') or {}).get('export_fingerprint') or 'legacy-receipt'
        from product_upload_source import current_source
        try:
            result['saved_source_version'] = current_source(row)['version']
        except (ValueError, KeyError, TypeError):
            pass  # Old/incomplete saves cannot unlock the complete prompt.
    if d.get('workflow_version') == 3:
        result['source'] = {k:d['source'].get(k) for k in ('id','rev','content_hash','path_display','name','size')}
        if d.get('lifecycle'):
            result['lifecycle'] = {k:d['lifecycle'].get(k) for k in ('state','reason','history','queued_at','checked_at')}
    return result
