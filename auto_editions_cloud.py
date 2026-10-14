"""Bounded cloud rendering against private persistent storage.

Transport and durable job store are injected. This module never reads a PSD,
starts Photoshop, allocates an edition, or submits a supplier order. It is not
enabled on production until hosted/role acceptance passes.
"""
from pathlib import Path
import re
import tempfile

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
                manifest=manifest,preparation_hash=identity['preparation'])


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
        metadata,response=self.integration.get_file_response(self.token,self.path(preparation_hash,asset['name']))
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

    def publish_output(self,job_id,path):
        destination=self.path(job_id,'output.jpg',cache=True)
        self.integration.ensure_folder_path(self.token,destination.rsplit('/',1)[0],root_path='/Sportscave Team Folder')
        # Only this derived cache key can be overwritten. The source and master
        # namespaces are never accepted by this method.
        metadata=self.integration.upload_local_file(self.token,destination,path,conflict='overwrite')
        if (not metadata or not metadata.get('id') or not metadata.get('rev')
                or metadata.get('size') != Path(path).stat().st_size
                or metadata.get('content_hash') != ae.file_hash(path,dropbox=True)):
            raise PreparationBlocked('Persistent Dropbox output was not confirmed.')
        return {'file_id':metadata['id'],'revision':metadata.get('rev'),
                'sha256':ae.file_hash(path),'bytes':Path(path).stat().st_size}

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
        destination=self.path(job_id,'output.jpg',cache=True)
        metadata=self.integration.get_metadata_if_exists(self.token,destination)
        if metadata is None:return
        if metadata.get('id')!=output.get('file_id') or metadata.get('rev')!=output.get('revision'):
            raise PreparationBlocked('Cache changed; automatic expiry refused.')
        self.integration.delete_path_recoverable(self.token,destination,root_path=self.ROOT+'/Cache')


def execute(job, assets, *, max_pixels=ae.WORKER_MAX_PIXELS):
    """Run one bounded worker job, reading only one master and requested patch.

    The bounded budget supports up to 60 MP TEST layouts on the existing standard
    service. Rendering and reference checks share a process-wide memory lock.
    Temporary disk is scratch only; inputs and results use persistent storage.
    """
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
        for asset in (manifest['master'],manifest['patches'][str(job['number'])]):
            name = asset['name']
            # Validate before giving the storage adapter a destination.
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',name):
                raise PreparationBlocked('Invalid prepared filename.')
            assets.fetch(job['preparation_hash'],asset,root/name)
        path=root/'output.jpg'
        rendered=ae.render_jpg(manifest,root,job['number'],path)
        if path.stat().st_size>MAX_OUTPUT_BYTES:
            raise PreparationBlocked('Rendered output exceeds the verified download limit.')
        output=assets.publish_output(job['id'],path)
        if output.get('sha256') != rendered['sha256']:
            raise PreparationBlocked('Persistent output verification failed.')
    return {**rendered,'output':output,'status':'Ready','test_only':True,
            'filename':f"edition-{job['number']:03}-of-{job['total']}-TEST-NOT-PRINT-READY.jpg"}
