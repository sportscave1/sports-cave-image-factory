"""Synthetic binary PSDs prove that cleanup changes only orphan history."""
import struct
import uuid
import pytest
from auto_editions_psd_repair import prune_history

def u32(n):return struct.pack('>I',n)

def fixture(path,*,orphan=True,unicode=False):
    used=str(uuid.uuid4());unused=str(uuid.uuid4())
    layers=b'layer-records-text-masks-and-channel-bytes:'+used.encode('utf-16-be' if unicode else 'ascii')
    def entry(identity):
        raw=b'liFD'+u32(8)+bytes([len(identity)])+identity.encode()+b'embedded-original-bytes'
        return struct.pack('>Q',len(raw))+raw+b'\0'*(-len(raw)%4)
    linked=entry(used)+(entry(unused) if orphan else b'')
    block=b'8BIMlnk2'+u32(len(linked))+linked
    rest=b'8BIMtest'+u32(4)+b'keep'
    section=u32(len(layers))+layers+u32(0)+block+rest
    header=b'8BPS\0\1'+b'\0'*20
    prefix=header+u32(0)+u32(4)+b'ICC!'
    composite=b'full-composite-and-every-pixel-byte'
    path.write_bytes(prefix+u32(len(section))+section+composite)
    return used,unused,layers,composite,rest

@pytest.mark.parametrize('unicode',[False,True])
def test_removes_only_unreferenced_embedding_and_retains_original(tmp_path,unicode):
    source=tmp_path/'original.psd';used,unused,layers,composite,rest=fixture(source,unicode=unicode)
    before=source.read_bytes();target=tmp_path/'repaired.psd'
    proof=prune_history(source,target);after=target.read_bytes()
    assert proof['removed_unreferenced_ids']==[unused] and not proof['pixels_changed']
    assert source.read_bytes()==before and layers in after and rest in after and after.endswith(composite)
    assert used.encode() in after and unused.encode() not in after
    assert prune_history(target,tmp_path/'second.psd') is None
    assert not (tmp_path/'second.psd').exists()

def test_no_orphans_and_unsupported_files_are_left_untouched(tmp_path):
    source=tmp_path/'original.psd';fixture(source,orphan=False)
    assert prune_history(source,tmp_path/'new.psd') is None
    source.write_bytes(b'not-a-PSD')
    assert prune_history(source,tmp_path/'new.psd') is None
    with pytest.raises(ValueError):prune_history(source,source)
