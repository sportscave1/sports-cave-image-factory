import json
from pathlib import Path
import pytest
import auto_editions as ae
from companion_package_identity import generation
from companion_package_repack import compact_retained
from auto_editions_package_limits import LEGACY_BYTES
from companion_acceptance_fixture import build


def fixture(tmp_path):
    source=build(tmp_path/'old','a'*32)
    import zipfile
    with zipfile.ZipFile(source) as z:manifest=json.loads(z.read('manifest.json'))
    ctx=dict(source=manifest['source'],number=100,total=100,automatic=True)
    (source.parent/'package-identity.json').write_text(json.dumps(dict(generation=generation(),sha256=ae.file_hash(source),preparation_hash=ae.fingerprint(manifest))))
    dest=tmp_path/'new'/'prepared.zip';dest.parent.mkdir()
    return source,dest,ctx


def test_repack_preserves_source_and_reconstructed_bytes(tmp_path,monkeypatch):
    source,dest,ctx=fixture(tmp_path);before=ae.file_hash(source)
    monkeypatch.setattr('auto_editions_preparation_geometry.matches',lambda *a:True)
    result,metrics=compact_retained(source,dest,ctx,generation(),LEGACY_BYTES,min_savings=65536)
    assert result==dest,metrics
    assert metrics['repack_saved_bytes']>65536 and ae.file_hash(source)==before
    assert json.loads((dest.parent/'package-identity.json').read_text())['sha256']==ae.file_hash(dest)


@pytest.mark.parametrize('where',['source','destination'])
def test_durable_session_descriptor_is_never_repacked(tmp_path,where):
    source,dest,ctx=fixture(tmp_path)
    parent=source.parent if where=='source' else dest.parent
    (parent/'upload-session.json').write_text('{}')
    assert compact_retained(source,dest,ctx,generation(),LEGACY_BYTES)[0]==source
    assert not dest.exists()


def test_changed_generation_refused_without_overwriting_either_packet(tmp_path):
    source,dest,ctx=fixture(tmp_path);before=ae.file_hash(source)
    with pytest.raises(ValueError,match='generation'):compact_retained(source,dest,ctx,'0'*64,LEGACY_BYTES)
    assert ae.file_hash(source)==before and not dest.exists()


def test_small_savings_and_existing_destinations_preserve_packet(tmp_path,monkeypatch):
    source,dest,ctx=fixture(tmp_path)
    result,metrics=compact_retained(source,dest,ctx,generation(),LEGACY_BYTES,min_savings=100000000)
    assert result==source and not dest.exists() and metrics['repack_outcome']=='insufficient byte sharing'
    dest.write_bytes(b'existing')
    assert compact_retained(source,dest,ctx,generation(),LEGACY_BYTES)[0]==source
    assert dest.read_bytes()==b'existing'
