"""Safe operator diagnostics. Unknown evidence never becomes a guessed cause."""
import re

RULES=(
 ('FONT_MISSING','Photoshop',('missing font','font is not installed','font unavailable','font is unavailable','fonts are unavailable','font is missing'),'A required PSD font is unavailable.','Install or repair the required font on the preparation computer, then confirm the correction and retry.'),
 ('EDITION_GEOMETRY','Photoshop',('psd edition total differs','not contained in its plaque','number does not lie inside'),'PSD edition text or plaque geometry does not match the required design.','Repair the mapped PSD to match the authoritative limit and plaque. Do not change issued edition numbers.'),
 ('PSD_MISSING','Dropbox',('path/not_found','file not found','mapped psd is missing'),'The mapped source PSD could not be found.','Restore or verify the existing mapped source. Do not silently select another PSD.'),
 ('DOWNLOAD_INTERRUPTED','Dropbox',('download failed','download interrupted'),'The artwork download was interrupted.','Check connectivity and retry; the worker will verify the source and downloaded bytes again.'),
 ('VALIDATION_FAILED','Companion',('checksum mismatch','geometry changed','file integrity','prepared file size changed'),'Prepared-file validation failed.','Inspect the recorded checksum, geometry and source evidence. Retry must pass the same validation.'),
 ('PHOTOSHOP_RPC','Photoshop',('0x800706be','rpc server is unavailable'),'Photoshop communication failed.','Check the companion and Photoshop diagnostics. Let owned recovery finish; do not remove an uncertain processor lock.'),
 ('VISUAL_AUTO_APPROVED','Photoshop',('auto approved:',),'Auto Approved under an exact owner-reviewed artwork policy.','Supplier certification remains separate; no human review was fabricated.'),
 ('VISUAL_POLICY_PENDING','Photoshop',('visual policy awaiting approval',),'Trusted visual reference policy awaits owner approval.','Review the exact original, numbered references and Shopify relationship; colour approval alone is insufficient.'),
 ('VISUAL_REFERENCE_CHANGED','Photoshop',('approved artwork reference bytes changed','differs from the approved original','storefront artwork comparison','live shopify product revision'),'Artwork or storefront reference evidence changed or is ambiguous.','Review the pinned reference comparison before approving this exact preparation.'),
 ('VISUAL_PROVIDER_FAILED','Companion',('visual source, reference or provider verification','visual reference or shopify identity verification'),'Automatic visual evidence could not be verified.','Retry the bounded evidence check; retain the preparation and original files.'),
 ('VISUAL_VALIDATION_FAILED','Photoshop',('automatic visual verification failed during',),'Automatic visual asset validation failed.','Inspect the recorded validation stage; retain the package and supplier safeguards.'),
 ('COLOUR_RECOVERED','Photoshop',('successful automatic colour recovery',),'Successful automatic colour recovery; verified package retained for visual review.','Complete the existing artwork and supplier reviews.'),
 ('PROFILE_APPROVED','Photoshop',('profile correction approved',),'Profile correction approved for this pinned source.','Preparation can reuse the approved source policy; supplier checks remain separate.'),
 ('COLOUR_POLICY_PENDING','Photoshop',('colour policy awaiting approval',),'Colour policy awaiting approval.','Review the proposed ICC profile against trusted print/reference evidence for this source group.'),
 ('PROFILE_INSPECTOR_FAILURE','Photoshop',('inspector failure','profile_inspector_failure','independent photoshop colour-profile evidence is incomplete'),'Inspector failure; source tagging is undetermined.','Review the file resource and Photoshop inspection; do not infer an untagged or corrupt PSD.'),
 ('COLOUR_INCOMPATIBLE','Photoshop',('print-colour incompatibility','colour_conversion_requires_approval'),'Print-colour compatibility requires review.','Obtain supplier evidence and separate conversion approval.'),
 ('SCRATCH_DISK','Photoshop',('scratch disk','scratch disks'),'Photoshop scratch disk failure.','Free Photoshop scratch storage and retry; retain the original and verified package.'),
 ('RECOVERY_RESUMED','Companion',('owned recovery resumed',),'Connection recovered; owned checkpoint processing resumed.','No action required.'),
 ('DISK_SPACE','Companion',('storage is low','no space left on device'),'Preparation computer has insufficient working storage.','Free working space without deleting unverified packages or originals.'),
 ('ICC_MISMATCH','Photoshop',('icc export mismatch','export_profile_changed','different colour profile','profile does not match','conflicting photoshop export'), 'Photoshop export failed — ICC profile mismatch.','Review the source/export profile evidence; do not assign a guessed profile.'),
 ('PROFILE_MISSING','Photoshop',('colour profile is unavailable','source_profile_requires_review','colour settings require owner review'), 'Original PSD has no verified colour profile.','Ask the owner to review the source colour settings.'),
 ('NUMBER_LAYER','Photoshop',('exactly one visible, editable edition-number','nested, locked or not independently editable'), 'PSD missing a uniquely editable edition-number layer.','Review the number layer in the original PSD.'),
 ('PLAQUE_AMBIGUOUS','Photoshop',('unique recognised collector plaque','ambiguous_roles'), 'PSD plaque identity is ambiguous.','Review the plaque role; retain the original geometry.'),
 ('NUMBER_FORMAT','Photoshop',('formatting cannot hold','number_width_requires_review'), 'Existing number formatting cannot hold the edition range.','Review the number format without changing issued editions.'),
 ('UPLOAD_INTERRUPTED','Dropbox',('upload/checkpoint failed','upload recovery exhausted','upload interrupted'), 'Dropbox upload interrupted — package retained for recovery.','Check connectivity and recovery receipts; do not rerender verified packages.'),
 ('TRANSFER_LIMIT','Dropbox',('transfer limit','package exceeds'), 'Artwork exceeds the verified transfer limit.','Review package size and the supported transfer policy.'),
 ('CONNECTION_INTERRUPTED','Companion',('timeouterror','readtimeout','connectionerror','transient preparation connection'), 'Connection interrupted; durable recovery is pending.','Restore the connection and check the next retry checkpoint.'),
 ('SOURCE_CHANGED','Dropbox',('source changed','source revision changed','linked source changed'), 'Pinned PSD identity or revision changed.','Review the exact mapped source before retrying.'),
 ('LEASE_EXPIRED','Companion',('lease expired','worker interrupted three times','superseded lease'), 'Preparation lease expired or recovery attempts were exhausted.','Check the preparation computer and retained checkpoint before retry.'),
 ('PROCESSOR_LOCK_HELD','Photoshop',('processor lock','lock ownership'), 'Photoshop processor lock is held or uncertain.','Inspect the existing processor; never remove an uncertain active lock.'),
)
STAGES=('Unknown','Claimed','Photoshop','Preparing','Uploading','Verifying','Review','Recovery','Discovery')
COMPONENTS=('Render','Companion','Photoshop','Dropbox','Database')


def explain(reason,stage='Unknown',component=None):
    value=str(reason or '').lower()
    for code,owner,patterns,message,action in RULES:
        if any(pattern in value for pattern in patterns):
            return dict(code=code,component=component if code=='CONNECTION_INTERRUPTED' and component in COMPONENTS else owner,description=message,recommended_action=action,
                        stage=stage if stage in STAGES else 'Unknown',severity='info' if code in ('RECOVERY_RESUMED','COLOUR_RECOVERED','PROFILE_APPROVED','VISUAL_AUTO_APPROVED') else 'warning' if code in ('COLOUR_POLICY_PENDING','VISUAL_POLICY_PENDING','VISUAL_REFERENCE_CHANGED') else 'error')
    return dict(code='CAUSE_UNDETERMINED',component=component if component in COMPONENTS else 'Companion',
                description='Cause not yet determined.',recommended_action='Inspect the referenced checkpoint and retained local diagnostics.',
                stage=stage if stage in STAGES else 'Unknown',severity='error')


def accepted(value):
    """Only predeclared codes and stage enums may cross the host/UI boundary."""
    if not isinstance(value,dict) or set(value)-{'code','stage','component','revision'}:raise ValueError('Safe diagnostic code required.')
    codes={r[0]:r for r in RULES}
    if value.get('code') not in {*codes,'CAUSE_UNDETERMINED'} or value.get('stage','Unknown') not in STAGES:
        raise ValueError('Unknown diagnostic code or stage.')
    rule=codes.get(value['code'])
    result=explain('',value.get('stage','Unknown'),value.get('component')) if not rule else explain(rule[2][0],value.get('stage','Unknown'),value.get('component'))
    if value.get('revision'):
        if not re.fullmatch(r'[a-zA-Z0-9._-]{1,64}',value['revision']):raise ValueError('Invalid diagnostic revision.')
        result['revision']=value['revision']
    return result


def operator_details(reason,stage='Unknown',code=None):
    """Operator advice is evidence based; it never authorises a retry itself."""
    value=explain(reason,stage)
    if code:
        try:value=accepted(dict(code=code,stage=stage))
        except ValueError:pass
    repair=value['code'] in {'FONT_MISSING','EDITION_GEOMETRY','NUMBER_LAYER','PLAQUE_AMBIGUOUS','NUMBER_FORMAT','PROFILE_MISSING','COLOUR_POLICY_PENDING','COLOUR_INCOMPATIBLE','ICC_MISMATCH','SOURCE_CHANGED','PSD_MISSING','VALIDATION_FAILED'}
    transient=value['code'] in {'DOWNLOAD_INTERRUPTED','UPLOAD_INTERRUPTED','CONNECTION_INTERRUPTED'}
    return {**value,'stage':stage if stage in STAGES and stage!='Unknown' else 'Stage unavailable',
        'manual_repair':repair,'retry_may_help':transient,
        'retry_guidance':'Correct the PSD, mapping or validation issue before retrying.' if repair else 'Retry may help after the connection recovers.' if transient else 'Inspect the recorded evidence before retrying; the cause is not established.'}


def technical_text(value):
    """Only existing textual errors are displayed; never expose grant objects."""
    text=str(value or '')[:4000]
    text=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~-]+',r'\1[redacted]',text)
    return re.sub(r'(?i)((?:token|secret|password|authorization|lease_token)\s*[=:]\s*)[^\s,;]+',r'\1[redacted]',text)
