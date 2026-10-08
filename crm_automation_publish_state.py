"""Compare effective authored content against immutable published content."""
from copy import deepcopy
from crm_automation_timing import single_delay


def document(value,defaults=None):
    from crm_html_workspace import html_document
    from crm_checkout_styles import MARKER
    doc=html_document(value)
    for key in ('copy_reviewed','counts','campaign_key','template_ref','market_audience','send_timing'):
        doc.pop(key,None)
    if defaults:doc.setdefault('html_sections',deepcopy(defaults))
    sections=doc.pop('middle_sections',None)
    if sections is None:sections=[{'type':'html','visible':True,'html':doc.get('custom_html','')}]
    doc.pop('custom_html',None)
    result=[]
    for section in sections:
        section=deepcopy(section)
        for key in ('id','name','html_number'):section.pop(key,None)
        if section['type']=='abandoned_checkout_products':section.update(type='html',html=MARKER)
        if result and section['type']=='html' and result[-1]['type']=='html' and section['visible']==result[-1]['visible']:
            result[-1]['html']+=section['html']
        else:result.append(section)
    doc['middle_sections']=result
    return doc


def effective(flow,reference=None):
    flow=single_delay(flow)
    flow.setdefault('inactive_days',180)
    flow.setdefault('exit_on_purchase',flow['trigger'] in ('abandoned','win_back'))
    reference={s['step_id']:s['document'].get('html_sections') for s in (reference or {}).get('emails',[])}
    for index,step in enumerate(flow['emails']):
        step.setdefault('enabled',True)
        step.setdefault('name','Email '+str(index+1))
        step['document']=document(step['document'],reference.get(step['step_id']))
    return flow


def published(store,row,conn=None):
    cfg=row['config']
    if not cfg.get('published_version'):return None
    if cfg.get('published_flow'):return deepcopy(cfg['published_flow'])
    def read(sql,args):
        return conn.execute(sql,args).fetchone() if conn else store.q(sql,args,True)
    job=read("SELECT snapshot FROM crm_automation_publish_jobs WHERE automation_id=%s AND publication_version=%s AND state='SUCCEEDED'",(row['id'],cfg['published_version']))
    flow=deepcopy(job['snapshot']['flow'] if job else cfg['published'])
    source=flow.get('emails',[]);by_id={s['step_id']:s for s in source};emails=[]
    for index,step in enumerate(row['steps']):
        saved=read('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=%s',(step['template_id'],step['template_version']))
        if not saved:raise ValueError('Published email snapshot is unavailable. Restore it before publishing.')
        content=saved['content'];email=deepcopy(by_id.get(step['step_id'],{}))
        email.update(step_id=step['step_id'],delay_seconds=step['delay_seconds'],document=content['document'],enabled=True)
        email.setdefault('name',step.get('name') or 'Email '+str(index+1));emails.append(email)
        if content.get('review_request'):flow['review_request']=content['review_request']
    if source:
        resolved={s['step_id']:s for s in emails}
        flow['emails']=[resolved.get(s['step_id'],s) for s in source]
    else:flow['emails']=emails
    return flow


def has_changes(store,row,flow=None,conn=None):
    live=published(store,row,conn)
    return live is None or effective(flow or row['config']['draft'],live)!=effective(live,live)


def label(row,changed=False):
    version=row['config'].get('published_version',0)
    state={'ACTIVE':'Live','PAUSED':'Paused','DRAFT':'Draft'}.get(row['status'],'Archived')
    return state+(' · v'+str(version) if version else '')+(' · Unpublished changes' if version and changed else '')
