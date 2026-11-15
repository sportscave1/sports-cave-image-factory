-- Manual operator rollback, only after reviewing the preserved snapshot.
-- Supply one reviewed UUID. This preserves the expanded draft in the revision audit.
-- Never run against an active automation. Do not drop audience/audit tables:
-- they contain history and are harmless to the previous release.
BEGIN;
-- SELECT id,status,config->'lifecycle_previous' FROM crm_automations WHERE id=:reviewed_id FOR UPDATE;
-- INSERT INTO crm_lifecycle_revisions(automation_id,revision,definition,actor)
-- SELECT id,(config->>'revision')::integer,config->'draft','reviewed rollback'
-- FROM crm_automations WHERE id=:reviewed_id AND status='DRAFT' ON CONFLICT DO NOTHING;
-- UPDATE crm_automations SET
-- config=config->'lifecycle_previous'->'config',steps=config->'lifecycle_previous'->'steps',updated_at=now()
-- WHERE id=:reviewed_id AND status='DRAFT' AND config ? 'lifecycle_previous';
ROLLBACK; -- Deliberately non-executable until the operator supplies the reviewed ID.
