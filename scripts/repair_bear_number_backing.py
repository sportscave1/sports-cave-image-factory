"""Owner-authorised Bear PSD normalization; produce a new pixel-exact copy only."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/studio')]

def main():
    import auto_editions as ae
    from auto_editions_local import processor_lease
    from scripts.photoshop_dispatch import run
    from PIL import Image,ImageChops
    source=Path.home()/'Documents/SportsCaveAutoEditions/4134d053e117486e3d53c515c6afa39043e0d0cc8977822a/input.psd'
    expected='d3efb6a77be9a24c161b5dd4618f5ea549de866c456a62b03dea24a22b5237b4'
    assert ae.file_hash(source,dropbox=True)==expected
    out=ROOT/'output/edition-repair/bear-normalized-v2';out.mkdir(parents=True,exist_ok=False)
    request=dict(input=str(source),output=str(out/'bear-repaired.psd'),root=str(out))
    inspector=(ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
    script=inspector+'\nvar REPAIR='+json.dumps(request)+';\n'+r'''
    (function(r){
      var doc=null,original=app.documents.length?app.activeDocument:null,dialogs=app.displayDialogs;
      var u=SCNumberLayer.proofUtilities;
      function png(name){var o=new PNGSaveOptions();o.interlaced=false;doc.saveAs(new File(r.root+'/'+name),o,true,Extension.LOWERCASE);}
      try{
        app.displayDialogs=DialogModes.NO;
        var opened=app.open(new File(r.input));doc=opened.duplicate('Bear repair copy');opened.close(SaveOptions.DONOTSAVECHANGES);
        var number=u.locate(doc.layers,318),background=u.locate(doc.layers,320);
        if(!number||!background||number.kind!==LayerKind.TEXT||number.textItem.contents!=='#61/100'||number.parent!==doc||background.name!=='Generative Fill 19 copy 2'||!background.visible)throw Error('reviewed_source_changed');
        if(doc.width.as('px')!==2953||doc.height.as('px')!==2088)throw Error('geometry_changed');
        png('before.png');
        number.visible=false;doc.selection.select([[2540,30],[2870,30],[2870,105],[2540,105]]);doc.selection.copy(true);doc.selection.deselect();
        var backing=doc.paste();backing.name='SC_EDITION_PLAQUE';
        var box=backing.bounds;backing.translate(UnitValue(2540-box[0].as('px'),'px'),UnitValue(30-box[1].as('px'),'px'));
        backing.move(doc,ElementPlacement.PLACEATBEGINNING);number.move(backing,ElementPlacement.PLACEBEFORE);number.visible=true;
        number.name='SC_EDITION_NUMBER';
        png('after.png');
        var options=new PhotoshopSaveOptions();options.layers=true;options.embedColorProfile=true;
        doc.saveAs(new File(r.output),options,true,Extension.LOWERCASE);
        return 'saved';
      }finally{if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);if(original)app.activeDocument=original;app.displayDialogs=dialogs;}
    })(REPAIR);
    '''
    lease=processor_lease()
    try:
        print(run(script))
        with Image.open(out/'before.png') as a,Image.open(out/'after.png') as b:
            assert a.size==b.size
            assert all(band.getbbox() is None for band in ImageChops.difference(a.convert('RGBA'),b.convert('RGBA')).split()),'Composite pixels changed'
        assert ae.file_hash(source,dropbox=True)==expected
        report=dict(original_unchanged=True,composite_pixels_exact=True,source_hash=expected,repaired_dropbox_hash=ae.file_hash(out/'bear-repaired.psd',dropbox=True),repaired_sha256=ae.file_hash(out/'bear-repaired.psd'))
        (out/'verified.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:lease.unlink()

if __name__=='__main__':main()
