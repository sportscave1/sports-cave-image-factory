"""Read-only projection of published columns and immutable checkout journeys.

Never calculates a new schedule, enrolls a customer or submits an email.
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from crm_logic import date, now
from crm_checkout_identity import display_name, recovered, block_label


def columns(steps):
    return [{'id':str(s.get('step_id') or 'legacy:'+str(i)),
             'label':'Email '+str(i+1), 'name':s.get('name') or 'Email '+str(i+1),
             'enabled':s.get('enabled',True),'published':s.get('published',True)} for i,s in enumerate(steps or [])]


def cell(label, tone='muted', reason='', due=None):
    return {'label':label,'tone':tone,'reason':reason or label,
            'due_at':due.isoformat() if due else None}


def pending(row, at):
    if recovered(row):return cell('Purchased','muted','Verified purchase; future reminders stopped')
    if row.get('archived_at'):return cell('Paused','gold','Flow archived')
    if row.get('automation_status')!='ACTIVE':return cell('Paused','gold','Flow is not active')
    request=row.get('enrollment_request') or {}
    if request.get('state')=='FAILED':return cell('Failed','red',request.get('result'))
    if request.get('state') in ('SAVING','QUEUED','CHECKING'):
        return cell('Awaiting worker',reason=request.get('result'))
    if request.get('state')=='DONE' and request.get('delivery')=='skipped':
        reason=request.get('result') or 'Not eligible'
        return cell('Suppressed' if reason in ('Suppressed','Unsubscribed','Opted out') else 'Not in flow',
                    'gold' if reason in ('Suppressed','Unsubscribed','Opted out') else 'red',reason)
    evaluation=row.get('evaluation') or {};reason=evaluation.get('reason','');result=evaluation.get('result','')
    if reason in ('local_suppression','provider_suppression','consent_unsubscribed','recovery_opted_out'):
        return cell('Suppressed','gold',block_label(reason))
    if reason=='recovered':return cell('Purchased')
    if reason=='recovery_recheck_required':return cell('Awaiting worker',reason=result)
    if result.startswith('Error:'):return cell('Failed','red',result)
    if reason or (result and result!='Added to flow'):
        return cell('Not in flow','red',result or block_label(reason))
    cutoff=date(row.get('auto_start_at'));created=date(row.get('created_at'))
    if cutoff and created and created<cutoff:
        return cell('Not in flow','red','Historical checkout — automatic enrollment is disabled')
    if not (row.get('analytics') or {}).get('email'):
        return cell('Contact needed','gold','Verified email is unavailable')
    # The current engine relies on Shopify's abandonment qualification. Do not
    # invent a second wait or infer eligibility from the presence of an email.
    activity=date(row.get('activity_at'))
    if not (row.get('analytics') or {}).get('shopify_abandoned') or (activity and activity>at):
        return cell('Qualifying',reason='Awaiting verified abandonment')
    return cell('Awaiting worker',reason='Awaiting eligibility verification and enrollment')


def progress(row, schema, at=None):
    at=at or now();steps=row.get('steps') or [];enrollment=row.get('enrollment_id')
    positions={str(s.get('step_id') or 'legacy:'+str(i)):i for i,s in enumerate(steps)}
    receipts={}
    for send in row.get('sends') or []:
        # Recovery history may contain other flows. Only this journey's
        # immutable step can provide evidence for a cell in this table.
        if not enrollment or str(send.get('enrollment_id'))!=str(enrollment):continue
        index=send.get('step')
        if not isinstance(index,int) or not 0<=index<len(steps):continue
        sid=str(steps[index].get('step_id') or 'legacy:'+str(index))
        if send.get('step_id') and str(send['step_id'])!=sid:continue
        receipts[sid]=send
    result=[];current=int(row.get('current_step') or 0)
    for col in schema:
        sid=col['id'];index=positions.get(sid);send=receipts.get(sid,{})
        status=send.get('status')
        if status=='ACCEPTED' and send.get('provider_id'):
            value=cell('Sent ✓','green','Accepted by Resend; inbox delivery is separate. See checkout details.')
        elif not col.get('published',True):
            value=cell('Not published',reason='Draft stage; publish successfully before it can join the live sequence')
        elif not col['enabled']:
            value=cell('Disabled',reason='Disabled in the published flow; no new delivery is eligible')
        elif recovered(row) or row.get('flow_status')=='RECOVERED':
            value=cell('Purchased',reason='Purchase recorded; future reminders stopped')
        elif not enrollment:
            value=pending(row,at) if col['enabled'] else cell('Disabled',reason='Disabled in the published flow')
        elif status=='FAILED':value=cell('Failed','red',send.get('error'))
        elif status=='BLOCKED':value=cell('Suppressed','gold',send.get('error'))
        elif row.get('flow_status')=='STOPPED':
            value=cell('Suppressed','gold',row.get('stop_reason') or 'Enrollment stopped')
        elif row.get('automation_status')!='ACTIVE' or row.get('archived_at'):
            value=cell('Paused','gold','Flow is not active; persisted schedule retained')
        elif status=='UNCERTAIN':value=cell('Confirming','gold','Provider outcome unknown; automatic replay is held')
        elif status in ('CLAIMED','SUBMITTING'):value=cell('Processing','gold','Worker is processing this step')
        elif row.get('flow_status')=='COMPLETED' and index is None:
            value=cell('Not applicable',reason='Historical completed enrollment; additional stages are not automatically backfilled')
        elif index is None:value=cell('Awaiting worker',reason='Live stage awaiting reconciliation into this active enrollment')
        elif index!=current and not steps[index].get('historical_pass') and not steps[index].get('delivery_complete'):
            value=cell('Waiting',reason='Waiting for the preceding stage and its configured delay')
        elif index==current and row.get('flow_status')=='ACTIVE':
            # Deferred sends (e.g. smart sending / rate limiting) can have a
            # later persisted deadline than the journey itself.
            deadlines=[d for d in (date(row.get('next_due_at')),date(send.get('due_at'))) if d]
            due=max(deadlines) if deadlines else None
            value=cell('Countdown','gold','Scheduled by the worker',due) if due else cell('Awaiting worker')
        else:value=cell('Unconfirmed','gold','No provider acceptance receipt recorded for this step')
        result.append(value)
    return result


def listing(rows, schema, timezone='Australia/Sydney', at=None):
    at=at or now()
    try:zone=ZoneInfo(timezone)
    except (ZoneInfoNotFoundError,ValueError):zone=ZoneInfo('Australia/Sydney')
    result=[]
    for row in rows:
        stamp=date(row.get('created_at'));local=stamp.astimezone(zone) if stamp else None
        request=row.get('enrollment_request') or {}
        result.append({'key':row['checkout_key'],'customer':display_name(row),
                       'created':f'{local.day} {local:%b}' if local else '—',
                       'created_full':local.strftime('%d %b %Y %H:%M:%S %Z') if local else 'Unavailable',
                       'cells':progress(row,schema,at),
                       'enrollment_progress':{k:request.get(k) for k in ('state','result')}})
    return result
