"""Small header snapshots derived from the existing companion queue states."""


def enrich_queues(queues):
    from morning_design_queue import list_jobs
    from upload_companion_page import estimated_progress
    from design_publish_ad import dashboard

    queues['upload']['display'] = True
    designs = []
    for job in list_jobs():
        stage = job['stage']
        state = 'waiting' if stage == 0 else 'running' if stage < 4 else 'complete' if stage == 4 else 'failed'
        percent, label = estimated_progress(job) if state == 'running' else (100 if state == 'complete' else 0, job['label'])
        designs.append({**job, 'state': state, 'percent': percent,
                        'label': label, 'estimated': state == 'running'})
    # Active work first, then the oldest queued job, then the latest outcome.
    designs = (sorted((j for j in designs if j['state'] == 'running'), key=lambda j: j.get('created_at', ''))
               + sorted((j for j in designs if j['state'] == 'waiting'), key=lambda j: j.get('created_at', ''))
               + sorted((j for j in designs if j['state'] not in ('running', 'waiting')),
                        key=lambda j: j.get('updated_at', ''), reverse=True))
    queues['design']['jobs'] = designs
    ads = dashboard()
    jobs = []
    for job in ads['jobs']:
        stage = job['stage']
        state = stage if stage in ('waiting', 'complete', 'failed') else 'running'
        # These are stage checkpoints, not a claim about image generation percentage.
        percent = {'waiting': 0, 'preparing': 10, 'opening': 20, 'generating': 40,
                   'posting': 80, 'complete': 100, 'failed': 0}[stage]
        jobs.append({**job, 'state': state, 'percent': percent, 'estimated': False})
    queues['ads'] = dict(enabled=ads['enabled'], online=ads['online'], jobs=jobs,
                         waiting=sum(job['state'] == 'waiting' for job in jobs))
    return queues
