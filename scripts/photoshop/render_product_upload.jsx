/* Opens only a new working copy. Never changes or closes a pre-existing doc. */
(function(r){
  var oldDialogs=app.displayDialogs,oldDoc=null,doc=null,ids={},closed=false,report={},failure=null;
  try{oldDoc=app.activeDocument;}catch(ignore){}
  for(var i=0;i<app.documents.length;i++)ids[String(app.documents[i].id)]=true;
  function encode(v){return SCPSDInspector.encode(v);}
  try{
    app.displayDialogs=DialogModes.NO;
    doc=app.open(new File(r.input));
    if(ids[String(doc.id)]){doc=null;throw Error('working_copy_already_open');}
    if(doc.mode!==DocumentMode.RGB||doc.bitsPerChannel!==BitsPerChannelType.EIGHT)throw Error('RGB8_required');
    if(r.profiles[0]!==doc.colorProfileName&&r.profiles[1]!==doc.colorProfileName)throw Error('source_profile_mismatch');
    // This conversion is only for the web image; the staged layered PSD and
    // the source are never saved with changed pixels, layers or profiles.
    if(doc.colorProfileName!=='sRGB IEC61966-2.1')doc.convertProfile('sRGB IEC61966-2.1',Intent.RELATIVECOLORIMETRIC,true,false);
    if(doc.colorProfileName!=='sRGB IEC61966-2.1')throw Error('web_profile_mismatch');
    var w=doc.width.as('px'),h=doc.height.as('px'),scale=Math.min(1,2000/Math.max(w,h));
    if(scale<1)doc.resizeImage(UnitValue(Math.round(w*scale),'px'),UnitValue(Math.round(h*scale),'px'),null,ResampleMethod.BICUBICSHARPER);
    report.dimensions=[doc.width.as('px'),doc.height.as('px')];
    var options=new PNGSaveOptions();options.interlaced=false;
    doc.saveAs(new File(r.output),options,true,Extension.LOWERCASE);
  }catch(error){failure=error;report.error=String(error);}
  finally{
    try{if(doc&&!ids[String(doc.id)]){doc.close(SaveOptions.DONOTSAVECHANGES);closed=true;}}
    finally{
      report.owned_document_closed=closed;
      app.displayDialogs=oldDialogs;if(oldDoc)try{app.activeDocument=oldDoc;}catch(ignore){}
      var file=new File(r.status);file.encoding='UTF8';if(!file.open('w'))throw Error('status_write_failed');
      try{file.write(encode(report));}finally{file.close();}
    }
  }
  if(failure)throw failure;
  return 'SC_PRODUCT_RENDERED';
})(SC_PRODUCT_RENDER);
