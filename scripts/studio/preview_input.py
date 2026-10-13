"""Bounded ordered raster input; no arbitrary selectors/scripts or replay."""
KEYS=frozenset({'Enter','Tab','Backspace','Escape','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Delete','Home','End'})

def validate_batch(data):
    events=data.get('events');page=data.get('page')
    if not isinstance(page,str) or not page or len(page)>100:
        raise ValueError('Input page required')
    if not isinstance(events,list) or not 1<=len(events)<=8:
        raise ValueError('Input batch size')
    total=0;result=[]
    for i,event in enumerate(events):
        if not isinstance(event,dict):raise ValueError('Input event')
        op=event.get('action')
        if op=='text':
            value=event.get('text')
            if set(event)!={'action','text'} or not isinstance(value,str):raise ValueError('Input text')
            total+=len(value)
            if not 0<len(value)<=2000 or total>2000:raise ValueError('Input text size')
        elif op=='key':
            if set(event)!={'action','key'} or event.get('key') not in KEYS:raise ValueError('Input key')
            if event['key']=='Enter' and i!=len(events)-1:raise ValueError('Submit must finish a batch')
        elif op=='scroll':
            if set(event)!={'action','delta'} or type(event.get('delta')) is not int or not -900<=event['delta']<=900:raise ValueError('Input scroll')
        else:raise ValueError('Input operation')
        result.append(dict(event))
    return result
