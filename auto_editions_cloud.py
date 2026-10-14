"""Bounded cloud rendering against private persistent storage.

Transport and durable job store are injected. This module never reads a PSD,
starts Photoshop, allocates an edition, or submits a supplier order. It is not
enabled on production until hosted/role acceptance passes.
"""
from pathlib import Path
import re
import tempfile
import time

import auto_editions as ae

MAX_OUTPUT_BYTES=64*1024*1024


class PreparationBlocked(ValueError):
    pass


def confirmed_job(unit, mapping, metadata, preparation):
    """Bind an authoritative allocation to a current approved preparation.

    Fulfilled/completed orders are eligible; allocation validity and cancellation
    are checked separately. Caller obtains these rows from the existing stores,
    never from client-supplied edition numbers.
    """
    manifest, approval = preparation['manifest'], preparation.get('approval')
    if ae.status(manifest, approval) != 'TEST READY':
        raise PreparationBlocked('Preparation needs visual and pixel-accuracy approval.')
    if (unit.get('allocation_valid') is not True or unit.get('identity_enforced') is not True
            or unit.get('invalidated_at') or unit.get('cancelled_at')
            or unit.get('duplicate_allocation_warning')
            or unit.get('status') not in ('assigned', 'completed', 'fulfilled')):
        raise PreparationBlocked('Allocation is missing, cancelled, invalid or ambiguous.')
    if not mapping or mapping.get('verified') is not True or mapping.get('state') != 'Linked':
        raise PreparationBlocked('An existing verified PSD mapping is required.')
    source = ae.source_identity(unit.get('shopify_product_gid'), metadata)
    if source != manifest['source'] or mapping.get('dropbox_file_id') != source['file_id']:
        raise PreparationBlocked('Mapping or Dropbox revision changed; prepare and approve again.')
    number, total = unit.get('edition_number'), unit.get('edition_total')
    if (type(number) is not int or type(total) is not int or not 1 <= number <= total
            or total != manifest['edition_total']):
        raise PreparationBlocked('Assigned edition does not match the prepared range.')
    variant = str(unit.get('shopify_variant_id') or unit.get('variant_id') or '')
    if not variant or variant not in preparation.get('variant_ids', []):
        raise PreparationBlocked('This exact variant has no approved compatible layout.')
    ordinal = unit.get('allocation_index') or unit.get('unit_ordinal')
    allocation = unit.get('id') or unit.get('allocation_id')
    if (type(allocation) is not int or allocation <= 0 or type(ordinal) is not int or ordinal <= 0
            or not unit.get('shopify_order_id') or not unit.get('shopify_line_item_id')):
        raise PreparationBlocked('Exact order-line allocation identity is required.')
    identity = dict(allocation_id=allocation,order_id=unit['shopify_order_id'],
                    line_id=unit['shopify_line_item_id'],ordinal=ordinal,variant_id=variant,
                    number=number,total=total,source=source,preparation=ae.fingerprint(manifest))
    return dict(id=ae.fingerprint(identity),identity=identity,number=number,total=total,
                manifest=manifest,preparation_hash=identity['preparation'],
                archive_labels={k:unit.get(k,'') for k in ('order_name','shopify_order_name','product_title','variant_title')})


def require_access(actor, *, setup=False):
    import os_accounts
    if not actor or not actor.get('id') or not all(os_accounts.can_access_page(actor,p) for p in ('Files','Orders')):
        raise PermissionError('An active Sports Cave account with Files and Orders access is required.')
    if setup and not os_accounts.is_admin(actor):
        raise PermissionError('An administrator must approve production assets.')
    return str(actor['id'])


class DropboxAssets:
    """Authenticated prepared assets in the existing team integration.

    This separate generated-assets folder never contains source PSDs. There is
    no catalogue discovery, shared-link creation, or existing mapping write.
    """
    ROOT='/Sportscave Team Folder/03_ASSETS/Auto Editions/Prepared'
    MAX_ASSET_BYTES=160*1024*1024

    def __init__(self, token, integration):
        self.token,self.integration=token,integration

    @classmethod
    def path(cls, digest, name, *, cache=False):
        if not re.fullmatch(r'[a-f0-9]{64}',digest) or not re.fullmatch(r'[A-Za-z0-9_-]+\.(png|jpg)',name):
            raise PreparationBlocked('Invalid prepared Dropbox asset identity.')
        return f"{cls.ROOT}/{'Cache' if cache else 'Masters'}/{digest}/{name}"

    def fetch(self, preparation_hash, asset, destination):
        from auto_editions_asset_cache import prepared_assets
        source_path=self.path(preparation_hash,asset['name'])
        if prepared_assets.copy(asset['sha256'],destination):return
        metadata,response=self.integration.get_file_response(self.token,source_path)
        try:
            size=metadata.get('size')
            if type(size) is not int or not 0<size<=self.MAX_ASSET_BYTES:
                raise PreparationBlocked('Prepared Dropbox asset exceeds the transfer limit.')
            length=0
            with Path(destination).open('wb') as output:
                for block in response.iter_content(chunk_size=1024*1024):
                    length+=len(block)
                    if length>size:raise PreparationBlocked('Prepared Dropbox asset length changed.')
                    output.write(block)
            if length!=size or ae.file_hash(destination)!=asset['sha256']:
                raise PreparationBlocked('Prepared Dropbox asset checksum changed.')
        finally:
            response.close()
        try:prepared_assets.remember(asset['sha256'],destination)
        except OSError:pass # Disposable cache availability must not block valid rendering.

    GENERATED_ROOT='/Sportscave Team Folder/03_ASSETS/Auto Editions/Generated JPGs'

    @classmethod
    def output_path(cls,job):
        labels=job.get('archive_labels',{})
        def slug(value,limit=60):
            return re.sub(r'[^A-Za-z0-9-]+','-',str(value)).strip('-')[:limit] or 'Artwork'
        order=slug(labels.get('order_name') or labels.get('shopify_order_name') or job['identity']['order_id'],40)
        title=slug(labels.get('product_title') or 'Artwork')
        variant_text=str(labels.get('variant_title') or job['identity']['variant_id'])
        size=re.search(r'\b(XL|L|M|S)\b',variant_text)
        variant=size.group(1) if size else slug(variant_text,24)
        # Full immutable job identity prevents collisions across line items,
        # master versions, edition assets and concurrent requests.
        name=f"{order}-{title}-Unit{job['identity']['ordinal']}-{job['number']:03}-of-{job['total']}-{variant}-TEST-{job['id']}.jpg"
        return f"{cls.GENERATED_ROOT}/{order}/TEST/{name}"

    def verify_output(self,output):
        metadata=self.integration.psd_open_metadata(self.token,output['file_id'],include_preview=False)
        if (not metadata or metadata.get('id')!=output['file_id']
                or metadata.get('rev')!=output['revision'] or metadata.get('size')!=output['bytes']
                or (output.get('dropbox_content_hash') and metadata.get('content_hash')!=output['dropbox_content_hash'])):
            raise PreparationBlocked('Saved JPG is unavailable or changed. Retry Open; ask an administrator to restore the archived revision if this persists.')
        path=metadata.get('path_display') or metadata.get('path_lower') or ''
        if not path.lower().startswith('/sportscave team folder/03_assets/auto editions/'):
            raise PreparationBlocked('Saved JPG is outside the approved Auto Editions location.')
        return metadata

    def output_response(self,output):
        # Dropbox now requires revision paths; the SDK rev argument is deprecated.
        # Reuse the authenticated team client and pin the archived bytes directly.
        if not re.fullmatch(r'[a-f0-9]+',str(output.get('revision',''))):
            raise PreparationBlocked('Invalid archived revision.')
        metadata,response=self.integration.team_space_client(self.token).files_download('rev:'+output['revision'])
        return self.integration._metadata_to_dict(metadata),response

    def publish_output(self,job,path):
        destination=self.output_path(job)
        self.integration.ensure_folder_path(self.token,destination.rsplit('/',1)[0],root_path='/Sportscave Team Folder')
        metadata=self.integration.get_metadata_if_exists(self.token,destination)
        if not metadata:
            try:
                metadata=self.integration.upload_local_file(self.token,destination,path,conflict='cancel')
            except Exception:
                # A concurrent/retried worker may have completed the same save.
                metadata=self.integration.get_metadata_if_exists(self.token,destination)
                if not metadata:raise
        digest=ae.file_hash(path,dropbox=True)
        if (not metadata or not metadata.get('id') or not metadata.get('rev')
                or metadata.get('size') != Path(path).stat().st_size
                or metadata.get('content_hash') != digest):
            raise PreparationBlocked('Archived Dropbox output differs; nothing was overwritten.')
        output={'file_id':metadata['id'],'revision':metadata['rev'],'path':metadata.get('path_display') or destination,
                'sha256':ae.file_hash(path),'dropbox_content_hash':digest,'bytes':Path(path).stat().st_size,
                'archive_status':'TEST','master_version':job['preparation_hash'],
                'identity':job['identity'],'labels':job.get('archive_labels',{})}
        self.verify_output(output)
        return output

    def publish_preparation(self,manifest,root):
        """Upload only immutable generated PNGs, resuming interrupted transfers.

        Caller verifies pixel proofs and administrator approval separately. No
        PSD, full-edition reference or existing mapping is ever uploaded here.
        """
        ae.validate_manifest(manifest)
        digest=ae.fingerprint(manifest)
        assets=[manifest['master']]+list(manifest['patches'].values())
        # Validate the entire local package before any cloud write.
        paths=[ae.asset_path(root,asset) for asset in assets]
        if any(not 0<p.stat().st_size<=self.MAX_ASSET_BYTES for p in paths):
            raise PreparationBlocked('Prepared asset exceeds the transfer limit.')
        folder=self.path(digest,'master.png').rsplit('/',1)[0]
        self.integration.ensure_folder_path(self.token,folder,root_path='/Sportscave Team Folder')
        records=[]
        for asset,path in zip(assets,paths):
            destination=self.path(digest,asset['name'])
            existing=self.integration.get_metadata_if_exists(self.token,destination)
            metadata=existing or self.integration.upload_local_file(self.token,destination,path,conflict='cancel')
            if (not metadata or not metadata.get('id') or not metadata.get('rev')
                    or metadata.get('content_hash')!=ae.file_hash(path,dropbox=True)
                    or metadata.get('size')!=path.stat().st_size):
                raise PreparationBlocked('Existing or uploaded asset differs; it was not overwritten.')
            records.append(dict(name=asset['name'],file_id=metadata['id'],revision=metadata['rev']))
        return dict(preparation_hash=digest,assets=records)

    def discard_cache(self,job_id,output):
        if output.get('archive_status'):return # Immutable archives are never expired or removed.
        destination=self.path(job_id,'output.jpg',cache=True)
        metadata=self.integration.get_metadata_if_exists(self.token,destination)
        if metadata is None:return
        if metadata.get('id')!=output.get('file_id') or metadata.get('rev')!=output.get('revision'):
            raise PreparationBlocked('Cache changed; automatic expiry refused.')
        self.integration.delete_path_recoverable(self.token,destination,root_path=self.ROOT+'/Cache')


def execute(job, assets, *, max_pixels=ae.WORKER_MAX_PIXELS):
    """Run one bounded worker job, reading only one master and requested patch.

    The bounded budget supports up to 95 MP TEST layouts on the existing standard
    service. Rendering and reference checks share a process-wide memory lock.
    Temporary disk is scratch only; inputs and results use persistent storage.
    """
    started=time.monotonic();timings={}
    manifest = ae.validate_manifest(job['manifest'])
    if ae.fingerprint(manifest) != job['preparation_hash']:
        raise PreparationBlocked('Preparation changed while queued.')
    if manifest['dimensions'][0]*manifest['dimensions'][1] > max_pixels:
        raise PreparationBlocked('This layout exceeds the verified worker memory budget.')
    if ae.fingerprint(job['identity']) != job['id'] or job['identity']['preparation'] != job['preparation_hash']:
        raise PreparationBlocked('Queued job identity changed.')
    if job['number'] != job['identity']['number'] or job['total'] != manifest['edition_total']:
        raise PreparationBlocked('Queued edition changed.')
    with tempfile.TemporaryDirectory(prefix='sc-edition-') as folder:
        root = Path(folder)
        step=time.monotonic()
        for asset in (manifest['master'],manifest['patches'][str(job['number'])]):
            name = asset['name']
            # Validate before giving the storage adapter a destination.
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',name):
                raise PreparationBlocked('Invalid prepared filename.')
            assets.fetch(job['preparation_hash'],asset,root/name)
        timings['prepared_assets_ms']=round((time.monotonic()-step)*1000)
        path=root/'output.jpg'
        step=time.monotonic()
        rendered=ae.render_jpg(manifest,root,job['number'],path)
        timings['compose_encode_validate_ms']=round((time.monotonic()-step)*1000)
        if path.stat().st_size>MAX_OUTPUT_BYTES:
            raise PreparationBlocked('Rendered output exceeds the verified download limit.')
        step=time.monotonic();output=assets.publish_output(job,path)
        timings['archive_and_verify_ms']=round((time.monotonic()-step)*1000)
        if output.get('sha256') != rendered['sha256']:
            raise PreparationBlocked('Persistent output verification failed.')
    from auto_editions_print import describe
    print_spec=describe(job.get('archive_labels',{}).get('variant_title',''),manifest)
    timings['worker_total_ms']=round((time.monotonic()-started)*1000)
    return {**rendered,'output':output,'status':'Ready','test_only':True,
            'timings':timings,
            'print_spec':print_spec,
            'retained':True, 'filename':Path(output.get('path') or f"edition-{job['number']:03}-of-{job['total']}-TEST-NOT-PRINT-READY.jpg").name}
