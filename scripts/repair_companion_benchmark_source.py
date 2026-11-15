"""One explicitly selected Steve Smith recovery copy; never edits the original.

Uses the existing exclusive processor lease and existing Photoshop instance.
Only the two reviewed visible layer names may change. No provider calls.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts/studio')]


def main():
    import psutil
    import auto_editions as ae
    from auto_editions_colour_policy import resolve
    from auto_editions_colour_source import stage_profile, inspect_psd
    from auto_editions_local import processor_lease
    from scripts.photoshop_dispatch import run
    from PIL import Image, ImageChops

    selection = json.loads((ROOT/'output/companion-phase1/recovery-selection.json').read_text())
    assert selection['product_gid'] == 'gid://shopify/Product/8117128986931'
    host_root = Path.home()/'Documents/SportsCaveAutoEditions'
    source = host_root/selection['job']/'input.psd'
    assert ae.file_hash(source) == selection['source_hashes']['sha256']
    host = json.loads((host_root/'host-status.json').read_text())
    assert host['status'] == 'Companion Connected' and time.time()-host['last_poll'] < 65
    assert host['companion_pid'] == selection['companion_pid'] and psutil.pid_exists(host['companion_pid'])
    assert sum(p.info['name'].lower() == 'photoshop.exe' for p in psutil.process_iter(['name'])) == 1
    config = host_root/'colour-configuration'
    icc, policy = resolve(selection['source'], json.loads((config/'policies.json').read_text()),
                          memberships=json.loads((config/'memberships.json').read_text()))
    assert policy == selection['policy']
    output = ROOT/'output/companion-phase1/source-repair'
    output.mkdir(exist_ok=False)
    assignment = stage_profile(source, output/'working.psd', icc)
    lease = processor_lease()
    safe_to_release = True
    try:
        request = dict(input=str(output/'working.psd'), output=str(output/'Steve Smith Ashes Hero Cricket Art - verified recovery.psd'), root=str(output))
        script = (ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig')
        script += '\nvar RECOVERY = '+json.dumps(request)+';\n'
        script += r'''
(function(r){
 var u=SCNumberLayer.proofUtilities, ids=u.openIds(), doc=null, original=app.documents.length?app.activeDocument:null,
     dialogs=app.displayDialogs, closed=false, report={};
 function write(name,value){var f=new File(r.root+'/'+name);f.encoding='UTF8';if(!f.open('w'))throw Error('repair_report_unavailable');try{f.write(SCPSDInspector.encode(value));}finally{f.close();}}
 function png(name){var o=new PNGSaveOptions();o.interlaced=false;o.compression=6;doc.saveAs(new File(r.root+'/'+name),o,true,Extension.LOWERCASE);}
 try{
  app.displayDialogs=DialogModes.NO;doc=app.open(new File(r.input));
  if(ids[String(doc.id)]){doc=null;throw Error('repair_copy_already_open');}
  var before=u.surface(doc), n=u.locate(doc.layers,36), p=u.locate(doc.layers,35);
  if(!n||!p||n.name!=='001 / 100'||p.name!=='limited-edition-plaque'||!n.visible||!p.visible||n.parent!==doc||p.parent!==doc||n.kind!==LayerKind.TEXT||n.textItem.contents!=='001 / 100')throw Error('reviewed_role_changed');
  var hn=u.locate(doc.layers,20), hp=u.locate(doc.layers,19);
  if(!hn||!hp||hn.visible||hp.visible)throw Error('hidden_duplicate_changed');
  if(doc.width.as('px')!==2835||doc.height.as('px')!==2004||doc.resolution!==72)throw Error('source_geometry_changed');
  png('before.png');
  n.name='SC_EDITION_NUMBER';p.name='SC_EDITION_PLAQUE';
  var options=new PhotoshopSaveOptions();options.layers=true;options.embedColorProfile=true;
  doc.saveAs(new File(r.output),options,true,Extension.LOWERCASE);doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
  doc=app.open(new File(r.output));if(ids[String(doc.id)]){doc=null;throw Error('repaired_copy_already_open');}
  var after=u.surface(doc), check=SCNumberLayer.compare(before,after,null,2);
  if(!check.ok)throw Error('repair_surface_changed:'+check.reason);
  if(u.locate(doc.layers,36).name!=='SC_EDITION_NUMBER'||u.locate(doc.layers,35).name!=='SC_EDITION_PLAQUE')throw Error('wrong_names_changed');
  png('after.png');report={before:before,after:after,verification:check,only_layer_names_changed:true};
  write('repair-surface.json',report);return 'SOURCE_REPAIR_NAMES_ONLY';
 }finally{
  if(doc&&!ids[String(doc.id)]){doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;}
  closed=true;for(var i=0;i<app.documents.length;i++)if(!ids[String(app.documents[i].id)])closed=false;
  app.displayDialogs=dialogs;if(original)try{app.activeDocument=original;}catch(ignored){}
  write('cleanup.json',{owned_document_closed:closed});
 }
})(RECOVERY);
'''
        safe_to_release = False
        try:
            assert run(script) == 'SOURCE_REPAIR_NAMES_ONLY'
        finally:
            try:
                safe_to_release = json.loads((output/'cleanup.json').read_text())['owned_document_closed'] is True
            except (OSError, ValueError, KeyError):
                pass
        assert safe_to_release
        repaired = Path(request['output'])
        assert inspect_psd(repaired)['icc'] == icc
        with Image.open(output/'before.png') as before, Image.open(output/'after.png') as after:
            assert before.mode == after.mode and before.size == after.size
            with ImageChops.difference(before, after) as difference:
                assert all(band.getbbox() is None for band in difference.split())
            if before.mode == 'RGBA':
                assert before.getchannel('A').getextrema() == (255, 255), 'Repair cannot invent an opaque background.'
        assert ae.file_hash(source) == selection['source_hashes']['sha256']
        report = dict(original_unchanged=True, source=selection['source'], assignment=assignment,
                      repaired_sha256=ae.file_hash(repaired), repaired_dropbox_hash=ae.file_hash(repaired,dropbox=True),
                      repaired_bytes=repaired.stat().st_size, pixels_exact=True,
                      layers_preserved=True, dimensions=[2835,2004], resolution=72,
                      source_revision_changed=False, uploaded=False)
        (output/'verified.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:
        if safe_to_release:
            lease.unlink()


if __name__ == '__main__':
    main()
