import json
import zipfile
from pathlib import Path
import pytest
import auto_editions as ae
from auto_editions_package import unpack
from test_auto_editions import package


def archive(tmp_path):
    source=tmp_path/'source';source.mkdir()
    manifest=package(source)
    (source/'manifest.json').write_text(json.dumps(manifest))
    (source/'original.png').write_bytes((source/'master.png').read_bytes())
    for n in (1,2):
        with ae.compose(manifest,source,n) as image:image.save(source/f'reference-{n}.png')
    path=tmp_path/'package.zip'
    with zipfile.ZipFile(path,'w') as output:
        for file in source.iterdir():output.write(file,file.name)
    dest=tmp_path/'unpacked';dest.mkdir()
    return path,dest,manifest


def test_package_recomputes_pixel_and_source_proofs(tmp_path):
    path,dest,m=archive(tmp_path)
    manifest,proofs=unpack(path,dest,m['source'],2,2)
    assert manifest==m and len(proofs)==3 and proofs[-1]['outside_number_exact']


@pytest.mark.parametrize('name',['../escape.png','master.psd','manifest.json'])
def test_package_rejects_paths_source_psds_and_duplicate_manifest(tmp_path,name):
    path,dest,m=archive(tmp_path)
    with zipfile.ZipFile(path,'a') as output:output.writestr(name,b'bad')
    with pytest.raises(ValueError):unpack(path,dest,m['source'],2,2)
    assert list(dest.iterdir())==[]


def test_package_rejects_different_linked_revision(tmp_path):
    path,dest,m=archive(tmp_path)
    with pytest.raises(ValueError,match='source'):unpack(path,dest,{**m['source'],'revision':'different'},2,2)
