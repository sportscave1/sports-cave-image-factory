"""Emit the reviewed, idempotent release SQL; never connects or sends email."""
from pathlib import Path


def sql():
    header=(Path(__file__).resolve().parents[1]/'templates/email_shared_header.html').read_text(encoding='utf-8')
    if '$approved$' in header:raise ValueError('Invalid release asset delimiter')
    return """DO $migration$
DECLARE saved crm_workspace_settings%ROWTYPE;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('migration:shared-email-branding:20261030'));
  IF EXISTS(SELECT 1 FROM crm_runtime_state WHERE key='migration:shared-email-branding:20261030') THEN RETURN; END IF;
  PERFORM 1 FROM crm_workspace_settings WHERE key IN ('email_default_header','email_default_footer') FOR UPDATE;
  IF (SELECT count(*) FROM crm_workspace_settings WHERE key IN ('email_default_header','email_default_footer'))<>2 THEN RAISE EXCEPTION 'Initialize shared email settings first'; END IF;
  INSERT INTO crm_runtime_state(key,value) VALUES('migration:shared-email-branding:20261030',jsonb_build_object(
    'settings',(SELECT jsonb_agg(to_jsonb(s)) FROM crm_workspace_settings s WHERE key IN ('email_default_header','email_default_footer','email_brand_defaults')),
    'drafts',(SELECT jsonb_agg(jsonb_build_object('id',id,'version',version,'document',document)) FROM crm_campaign_drafts),
    'templates',(SELECT jsonb_agg(jsonb_build_object('id',id,'version',version,'content',content)) FROM crm_templates WHERE content->>'format' IN ('campaign_blocks_v1','campaign_brand_section_v1','automation_delivery_v1')),
    'flows',(SELECT jsonb_agg(jsonb_build_object('id',id,'config',config,'steps',steps)) FROM crm_automations)));
  INSERT INTO crm_settings_history(key,version,value,actor)
    SELECT key,version,value,'release:shared-email-branding:20261030:backup' FROM crm_workspace_settings WHERE key='email_default_header';
  UPDATE crm_workspace_settings SET value=jsonb_set(value,'{html}',to_jsonb($approved$"""+header+"""$approved$::text)),
    version=version+1,updated_by='release:shared-email-branding:20261030',updated_at=now()
    WHERE key='email_default_header' AND btrim(value->>'html')<>btrim($approved$"""+header+"""$approved$::text) RETURNING * INTO saved;
  IF FOUND THEN
    INSERT INTO crm_settings_history(key,version,value,actor) VALUES(saved.key,saved.version,saved.value,'release:shared-email-branding:20261030');
  END IF;
END $migration$;
"""


if __name__=='__main__':print(sql())
