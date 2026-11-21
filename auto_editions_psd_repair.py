"""Remove unreferenced embedded history from a staged PSD, byte for byte.

Photoshop can reject obsolete embedded assets even when no layer uses them.
Keep every layer, mask, text descriptor, referenced object, profile and composite.
The original is never overwritten. Unsupported structures remain untouched.
"""
import hashlib
import mmap
from pathlib import Path
import uuid


def prune_history(source,destination):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('A new staged PSD repair destination is required.')
    with source.open('rb') as file,mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
        if len(data)<34 or data[:6]!=b'8BPS\0\1':return None
        def integer(offset,size=4):
            if offset<0 or offset+size>len(data):raise ValueError('Truncated PSD repair structure.')
            return int.from_bytes(data[offset:offset+size],'big')
        resources=30+integer(26)
        if resources+4>len(data):return None
        outer=resources+4+integer(resources)
        if outer+8>len(data):return None
        end=outer+4+integer(outer)
        if end>len(data):return None
        layer_start=outer+8;layer_end=layer_start+integer(outer+4)
        if layer_end+4>end:return None
        cursor=layer_end+4+integer(layer_end)
        if cursor>end:return None
        changes=[];removed=[]
        references=data[layer_start:layer_end].lower()
        while cursor+12<=end:
            signature=data[cursor:cursor+4];key=data[cursor+4:cursor+8]
            if signature not in (b'8BIM',b'8B64'):return None
            width=8 if signature==b'8B64' else 4
            start=cursor+8+width;length=integer(cursor+8,width)
            stop=start+length;padded=stop+(-length%4)
            if padded>end:return None
            if key==b'lnk2':
                entries=[];pos=start;discarded=[]
                while pos+8<=stop:
                    size=integer(pos,8);body=pos+8;tail=body+size;next_pos=tail+(-size%4)
                    if size<9 or next_pos>stop:return None
                    count=data[body+8];identity=data[body+9:body+9+count]
                    if body+9+count>tail:return None
                    try:uuid.UUID(identity.decode('ascii'))
                    except (ValueError,UnicodeError):return None
                    used=(identity.lower() in references
                          or identity.decode('ascii').lower().encode('utf-16-be') in references)
                    if data[body:body+4]==b'liFD' and not used:discarded.append(identity.decode('ascii'))
                    else:entries.append((pos,next_pos))
                    pos=next_pos
                if pos!=stop:return None
                if discarded:
                    new_length=sum(b-a for a,b in entries)
                    changes.append((cursor,padded,data[cursor:cursor+8]+new_length.to_bytes(width,'big'),entries))
                    removed.extend(discarded)
            cursor=padded
        if not changes:return None
        reduction=sum(b-a-len(header)-sum(y-x for x,y in entries) for a,b,header,entries in changes)
        def copy(output,a,b):
            for pos in range(a,b,4*1024*1024):output.write(data[pos:min(pos+4*1024*1024,b)])
        try:
            with destination.open('xb') as output:
                copy(output,0,outer);output.write((end-outer-4-reduction).to_bytes(4,'big'))
                pos=outer+4
                for a,b,header,entries in changes:
                    copy(output,pos,a);output.write(header)
                    for x,y in entries:copy(output,x,y)
                    pos=b
                copy(output,pos,len(data))
            with destination.open('rb') as repaired,mmap.mmap(repaired.fileno(),0,access=mmap.ACCESS_READ) as after:
                # These three byte ranges contain all layers/channels/masks, ICC
                # and other resources, and the saved full-canvas composite.
                checks=[(0,outer,0),(outer+4,changes[0][0],outer+4),(end,len(data),end-reduction)]
                for a,b,target in checks:
                    for pos in range(a,b,4*1024*1024):
                        block=data[pos:min(pos+4*1024*1024,b)]
                        if block!=after[target+pos-a:target+pos-a+len(block)]:raise ValueError('PSD layer/pixel preservation failed.')
            return dict(removed_unreferenced_ids=removed,removed_bytes=reduction,
                layer_info_sha256=hashlib.sha256(data[layer_start:layer_end]).hexdigest(),
                original_preserved=True,pixels_changed=False)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
