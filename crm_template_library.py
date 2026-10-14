"""Automation library metadata and independent, source-preserving snapshots."""
from copy import deepcopy
import json
import uuid
from crm_template_cache import cached, invalidate

GROUPS=('Defaults','Post Purchase','Welcome Series','Abandoned Checkout','Win Back','Lifestyle & Product','Other Templates')
PREFIX='email_library_builtin_v1:'


def group_for(row):
    explicit=row.get('library_group') or row.get('content',{}).get('library_group')
    if explicit in GROUPS:return explicit
    text=(str(row.get('id',''))+' '+row['name']).lower().replace('_',' ').replace('-',' ')
    if any(word in text for word in ('lifestyle','frame','wall preview','personalised','personalized')):return 'Lifestyle & Product'
    if any(word in text for word in ('post purchase','collected artwork','build your collection','build collection','thank you')):return 'Post Purchase'
    if any(word in text for word in ('welcome','collector introduction')):return 'Welcome Series'
    if any(word in text for word in ('win back','re engagement','reengagement')):return 'Win Back'
    if any(word in text for word in ('abandoned','recovery')):return 'Abandoned Checkout'
    return 'Other Templates'


def rows(store):
    from crm_campaign_library import library_rows
    result=library_rows(store)
    # Built-in designs have stable non-UUID identities. Store only explicit edits
    # in existing runtime storage, without creating duplicate template records.
    edits=cached(store,('builtin-library-metadata',),lambda:store.q(
        "SELECT key,value->>'name' AS name,value->>'group' AS library_group,value->>'revision' AS revision FROM crm_runtime_state WHERE key LIKE %s",(PREFIX+'%',)))
    edits={r['key'][len(PREFIX):]:r for r in edits}
    for row in result:
        edit=edits.get(str(row['id']))
        if row.get('builtin'):
            row['base_version']=row['version'];row['revision']=int(edit['revision']) if edit else 0
            if edit:row.update(name=edit['name'],library_group=edit['library_group'],version=row['version']+row['revision'])
    # Keep legacy source functions/IDs and saved edits available without offering
    # five overlapping built-ins. User-created templates are never deleted.
    legacy={'builtin-collector-v1-collected-artwork','builtin-collector-v1-build-collection'}
    legacy.update('builtin-collector-stage-v2-post_purchase-'+str(n) for n in (1,2,3))
    kept=[]
    for row in result:
        if row.get('builtin') and row['id'] in legacy:
            if not row.get('revision'):continue
            row['library_group']='Other Templates'
        kept.append(row)
    return kept


def source(store,row):
    from crm_campaign_library import template_html
    if row.get('builtin') and row.get('revision',0):
        saved=cached(store,('builtin-library-body',row['id'],row['revision']),lambda:store.state(PREFIX+row['id']))
        if saved.get('revision')!=row['revision']:raise ValueError('Template changed. Reopen it before editing.')
        return saved['html']
    return template_html(store,row)


def section_source(store,row):
    """Reusable body only; saved section groups exclude fixed email branding."""
    from crm_campaign_library import template_sections
    parts=template_sections(store,row)
    return dict(html=source(store,row) if parts is None else '',sections=parts,name=row['name'])


def save_builtin(store,user,row,name,html,group):
    from crm_navigation import require
    from crm_campaign_content import new_document,validate_document
    require(user,'crm_templates_manage')
    if not row.get('builtin') or group not in GROUPS:raise ValueError('Choose a template group.')
    if not name.strip() or len(name)>150:raise ValueError('Use a template name of 1–150 characters.')
    doc=new_document();doc.update(content_mode='HTML',custom_html=html);validate_document(doc)
    key=PREFIX+str(row['id'])
    with store.db() as conn:
        conn.execute("INSERT INTO crm_runtime_state(key,value) VALUES(%s,'{\"revision\":0}'::jsonb) ON CONFLICT DO NOTHING",(key,))
        old=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s FOR UPDATE',(key,)).fetchone()['value']
        if old['revision']!=row.get('revision',0):raise ValueError('Template changed elsewhere. Reopen it before saving.')
        value=dict(revision=old['revision']+1,name=name.strip(),html=html,group=group)
        conn.execute('UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps(value),key))
    invalidate()


def apply_template(store,doc,identity,version,*,confirmed=False):
    """Replace only middle content; never copy subject, defaults or send settings."""
    from crm_campaign_library import template_sections
    from crm_middle_sections import middle_sections,commit_middle
    from crm_campaign_content import validate_document
    row=next((r for r in rows(store) if str(r['id'])==str(identity) and r['version']==version),None)
    if row is None:raise ValueError('Template changed. Reopen the template picker.')
    old=middle_sections(doc)
    if any(s.get('html','').strip() or s['type'] not in ('html','image') for s in old) and not confirmed:
        raise ValueError('Confirm replacing the current email content.')
    incoming=template_sections(store,row) if not row.get('builtin') else None
    if incoming is None:incoming=[dict(id=uuid.uuid4().hex,type='html',visible=True,html_number=1,html=source(store,row),css_version=1)]
    else:
        incoming=deepcopy(incoming)
        for section in incoming:section['id']=uuid.uuid4().hex
    for section in incoming:
        if section['type']=='discount':section['offer']=deepcopy(doc.get('recovery_discount'))
    proposed=deepcopy(doc)
    commit_middle(proposed,incoming)
    proposed.update(content_mode='HTML',copy_reviewed=False,template_ref=dict(id=str(row['id']),version=row['version'],name=row['name']))
    validate_document(proposed);doc.update(proposed)
