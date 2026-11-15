/* Synthetic local fixture only; never opens or saves an existing artwork. */
function SCV19Fixture(r) {
    var root = new Folder(r.root).fsName.toLowerCase(), path = new File(r.path).fsName.toLowerCase();
    if (path.indexOf(root + "\\") !== 0 && path.indexOf(root + "/") !== 0) throw Error("unsafe_fixture_path");
    if (new File(r.path).exists || r.width*r.height > 25000000) throw Error("unsafe_fixture_request");
    var old = app.documents.length ? app.activeDocument : null, dialogs = app.displayDialogs, doc = null, closed = true;
    app.displayDialogs = DialogModes.NO;
    try {
        var font = app.fonts.getByName("ArialMT").postScriptName;
        doc = app.documents.add(UnitValue(r.width,"px"),UnitValue(r.height,"px"),300,"V19 synthetic artwork",
            NewDocumentMode.RGB,DocumentFill.WHITE,1,BitsPerChannelType.EIGHT,"sRGB IEC61966-2.1");
        closed = false;
        function rectangle(name, x0, y0, x1, y1, values) {
            var layer=doc.artLayers.add();layer.name=name;doc.activeLayer=layer;
            var colour=new SolidColor();colour.rgb.red=values[0];colour.rgb.green=values[1];colour.rgb.blue=values[2];
            doc.selection.select([[x0,y0],[x1,y0],[x1,y1],[x0,y1]]);doc.selection.fill(colour);doc.selection.deselect();return layer;
        }
        for (var n=0;n<24;n++) {
            var x=(n%6)*r.width/6,y=Math.floor(n/6)*r.height/5;
            rectangle("Synthetic artwork " + n,x,y,x+r.width/6,y+r.height/5,[(n*47)%256,(n*83)%256,(n*137)%256]);
        }
        rectangle("SC_EDITION_PLAQUE",r.width*0.60,r.height*0.83,r.width*0.98,r.height*0.98,[230,230,230]);
        var text=doc.artLayers.add();text.kind=LayerKind.TEXT;text.name="SC_EDITION_NUMBER";
        text.textItem.font=font;text.textItem.size=UnitValue(r.height*0.025,"px");
        text.textItem.position=[UnitValue(r.width*0.69,"px"),UnitValue(r.height*0.93,"px")];
        text.textItem.contents="001 / 100";
        var ink=new SolidColor();ink.rgb.red=10;ink.rgb.green=20;ink.rgb.blue=30;text.textItem.color=ink;
        var options=new PhotoshopSaveOptions();options.layers=true;options.embedColorProfile=true;
        doc.saveAs(new File(r.path),options,true,Extension.LOWERCASE);
    } finally {
        try { if(doc) {doc.close(SaveOptions.DONOTSAVECHANGES);closed=true;} }
        finally {
            app.displayDialogs=dialogs;if(old)try{app.activeDocument=old;}catch(ignore){}
            var status=new File(r.root+"/fixture-status.json");status.encoding="UTF8";
            if(status.open("w"))try{status.write(SCPSDInspector.encode({owned_document_closed:closed}));}finally{status.close();}
        }
    }
    return "V19_SYNTHETIC_FIXTURE_CREATED";
}
SCV19Fixture(SC_V19_FIXTURE_REQUEST);
