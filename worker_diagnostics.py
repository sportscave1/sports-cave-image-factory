"""Safe operator diagnostics. Unknown evidence never becomes a guessed cause."""
import re

RULES=(
 ('RECOVERY_RESUMED','Companion',('owned recovery resumed',),'Connection recovered; owned checkpoint processing resumed.','No action required.'),
 ('DISK_SPACE','Companion',('storage is low','no space left on device'),'Preparation computer has insufficient working storage.','Free working space without deleting unverified packages or originals.'),
 ('ICC_MISMATCH','Photoshop',('different colour profile','profile does not match','conflicting photoshop export'), 'Photoshop export failed — ICC profile mismatch.','Review the source/export profile evidence; do not assign a guessed profile.'),
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
                        stage=stage if stage in STAGES else 'Unknown',severity='info' if code=='RECOVERY_RESUMED' else 'error')
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
