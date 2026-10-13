/* Sports Cave PSD edition inspection V1. Read-only; only disposable staged copies are opened. */
var SCPSDInspector = (function () {
    function encode(v) {
        if (v === null || v === undefined) return "null";
        if (typeof v === "string") return '"' + v.replace(/\\/g,"\\\\").replace(/"/g,'\\"').replace(/\r/g,"\\r").replace(/\n/g,"\\n").replace(/\t/g,"\\t").replace(/[\x00-\x1f]/g,function(c){return "\\u"+("0000"+c.charCodeAt(0).toString(16)).slice(-4);}) + '"';
        if (typeof v === "number") return isFinite(v) ? String(v) : "null";
        if (typeof v === "boolean") return v ? "true" : "false";
        var a=[],k;
        if (v instanceof Array) { for(k=0;k<v.length;k++)a.push(encode(v[k]));return "["+a.join(",")+"]"; }
        for(k in v)if(v.hasOwnProperty(k))a.push(encode(k)+":"+encode(v[k]));
        return "{"+a.join(",")+"}";
    }
    function attempt(fn,fallback) {try{return fn();}catch(e){return fallback;}}
    function descValue(d,k,depth) {
        if(depth>6)return null;
        var t=d.getType(k);
        if(t===DescValueType.STRINGTYPE)return d.getString(k);
        if(t===DescValueType.BOOLEANTYPE)return d.getBoolean(k);
        if(t===DescValueType.INTEGERTYPE)return d.getInteger(k);
        if(t===DescValueType.DOUBLETYPE)return d.getDouble(k);
        if(t===DescValueType.UNITDOUBLE)return {value:d.getUnitDoubleValue(k),unit:attempt(function(){return typeIDToStringID(d.getUnitDoubleType(k));},"unknown")};
        if(t===DescValueType.ENUMERATEDTYPE)return attempt(function(){return typeIDToStringID(d.getEnumerationValue(k));},"unknown");
        if(t===DescValueType.OBJECTTYPE)return descriptor(d.getObjectValue(k),depth+1);
        if(t===DescValueType.LISTTYPE){var list=d.getList(k),a=[];for(var i=0;i<Math.min(list.count,100);i++)a.push(descValue(list,i,depth+1));return a;}
        return {unsupported_type:String(t)};
    }
    function descriptor(d,depth) {
        var o={};
        for(var i=0;i<d.count;i++){var k=d.getKey(i),name=attempt(function(){return typeIDToStringID(k);},"");if(!name)name=attempt(function(){return typeIDToCharID(k);},String(k));
            // Large EngineData/raw pixels are not retained; style descriptors are sufficient for review.
            if(name==="EngineData")continue;
            o[name]=attempt(function(){return descValue(d,k,depth);},null);
        }return o;
    }
    function layerDescriptor(layer) {
        var r=new ActionReference();r.putIdentifier(charIDToTypeID("Lyr "),layer.id);return executeActionGet(r);
    }
    function bounds(layer) {return attempt(function(){var b=layer.bounds;return [b[0].as("px"),b[1].as("px"),b[2].as("px"),b[3].as("px")];},null);}
    function inspect(doc,request) {
        var out={engine:"Photoshop",engine_version:app.version,script_version:1,complete:true,layers:[],warnings:[],
            document:{width_px:doc.width.as("px"),height_px:doc.height.as("px"),resolution:doc.resolution,
            mode:String(doc.mode),bits_per_channel:String(doc.bitsPerChannel),profile:attempt(function(){return doc.colorProfileName;},null)}};
        var objectCount=0;
        function walk(container,path,visible,locked,chain,depth,owner) {
            for(var i=0;i<container.layers.length;i++){
                var l=container.layers[i],id=attempt(function(){return l.id;},null),entry={index:i,layer_id:id,name:l.name};
                var current=path.concat([entry]),vis=visible && l.visible,lock=locked || attempt(function(){return l.allLocked;},true);
                var row={layer_id:id,path:current,smart_object_chain:chain,visible:vis,locked:lock,bounds_px:bounds(l),kind:l.typename==="LayerSet"?"group":String(l.kind)};
                if(l.typename==="LayerSet"){out.layers.push(row);walk(l,current,vis,lock,chain,depth,owner);continue;}
                if(l.kind===LayerKind.TEXT){
                    row.kind="text";row.text=attempt(function(){return l.textItem.contents;},null);
                    row.editable=!lock && row.text!==null;
                    var ti=l.textItem;
                    row.layout={font:attempt(function(){return ti.font;},null),size_pt:attempt(function(){return ti.size.as("pt");},null),
                        tracking:attempt(function(){return ti.tracking;},null),leading_pt:attempt(function(){return ti.leading.as("pt");},null),
                        justification:attempt(function(){return String(ti.justification);},null),orientation:attempt(function(){return String(ti.direction);},null),
                        text_kind:attempt(function(){return String(ti.kind);},null),position_px:attempt(function(){return [ti.position[0].as("px"),ti.position[1].as("px")];},null),
                        faux_bold:attempt(function(){return ti.fauxBold;},null),faux_italic:attempt(function(){return ti.fauxItalic;},null)};
                    row.text_descriptor=attempt(function(){var d=layerDescriptor(l);return descriptor(d.getObjectValue(stringIDToTypeID("textKey")),0);},null);
                    var fonts=[],styles=row.text_descriptor?row.text_descriptor.textStyleRange:null;
                    if(styles instanceof Array)for(var f=0;f<styles.length;f++){var st=styles[f].textStyle;if(st&&st.fontPostScriptName)fonts.push(st.fontPostScriptName);}
                    if(!fonts.length&&row.layout&&row.layout.font)fonts.push(row.layout.font);
                    row.fonts=[];for(var f2=0;f2<fonts.length;f2++)row.fonts.push({postscript_name:fonts[f2],installed:attempt((function(name){return function(){app.fonts.getByName(name);return true;};})(fonts[f2]),false)});
                    out.layers.push(row);continue;
                }
                if(l.kind===LayerKind.SMARTOBJECT){
                    row.kind="smart_object";var so=attempt(function(){var d=layerDescriptor(l);return descriptor(d.getObjectValue(stringIDToTypeID("smartObject")),0);},null);
                    row.smart_object=so;out.layers.push(row);
                    var reference=so?String(so.fileReference||""):"";
                    if(!so||so.linked!==false&&so.linked!==undefined){out.warnings.push({code:"linked_or_unknown_smart_object",path:current});continue;}
                    if(!/\.(psd|psb)$/i.test(reference)){row.smart_object_readiness="raster_or_unsupported";continue;}
                    if(depth>=request.smart_object_depth||objectCount>=request.smart_object_limit){out.complete=false;out.warnings.push({code:"smart_object_limit",path:current});continue;}
                    objectCount++;var before={},child=null,selected=owner.activeLayer;
                    for(var b=0;b<app.documents.length;b++)before[String(app.documents[b].id)]=true;
                    try {
                        app.activeDocument=owner;owner.activeLayer=l;
                        executeAction(stringIDToTypeID("placedLayerEditContents"),undefined,DialogModes.NO);
                        child=app.activeDocument;
                        if(child.id===owner.id||before[String(child.id)]){out.complete=false;out.warnings.push({code:"smart_object_busy_or_unopened",path:current});child=null;continue;}
                        var link=chain.concat([{layer_id:id,path:current,embedded:true,file_reference:reference}]);
                        walk(child,current,vis,lock,link,depth+1,child);
                    } catch(e){out.complete=false;out.warnings.push({code:"smart_object_unavailable",path:current});}
                    finally {if(child&&!before[String(child.id)])child.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=owner;owner.activeLayer=selected;}
                }else{row.kind="raster";out.layers.push(row);}
            }
        }
        walk(doc,[],true,false,[],0,doc);return out;
    }
    function inside(root,file){var base=new Folder(root).fsName.toLowerCase().replace(/[\\\/]+$/,""),p=new File(file).fsName.toLowerCase();return p.indexOf(base+"\\")===0||p.indexOf(base+"/")===0;}
    function run(request){
        if(!request||request.entries.length>10||!inside(request.output_root,request.report_path)||!/\.json$/i.test(request.report_path))throw Error("Unsafe inspection request");
        var oldDialogs=app.displayDialogs,oldDocument=app.documents.length?app.activeDocument:null,results=[];
        app.displayDialogs=DialogModes.NO;
        try{
            for(var i=0;i<request.entries.length;i++){
                var e=request.entries[i],result={product_gid:e.product_gid,dropbox_file_id:e.dropbox_file_id,dropbox_revision:e.dropbox_revision},doc=null;
                var start=new Date().getTime(),existing={};
                if(!inside(request.stage_root,e.work_path)||!/\.psd$/i.test(e.work_path))throw Error("Only staged PSD copies can be inspected");
                for(var j=0;j<app.documents.length;j++)existing[String(app.documents[j].id)]=true;
                try{
                    doc=app.open(new File(e.work_path));
                    if(existing[String(doc.id)]){doc=null;throw Error("Staged document is already open");}
                    result.inspection=inspect(doc,request);
                }catch(error){result.error="Photoshop inspection unavailable";result.error_number=attempt(function(){return error.number;},null);}
                finally{if(doc&&!existing[String(doc.id)])doc.close(SaveOptions.DONOTSAVECHANGES);}
                result.elapsed_ms=new Date().getTime()-start;results.push(result);
            }
        }finally{app.displayDialogs=oldDialogs;if(oldDocument)attempt(function(){app.activeDocument=oldDocument;},null);}
        var report=new File(request.report_path);report.encoding="UTF8";if(!report.open("w"))throw Error("Report cannot be written");
        try{report.write(encode({read_only:true,documents:results}));}finally{report.close();}
        return "SC_INSPECTION_COMPLETE:"+results.length;
    }
    return {run:run,inspect:inspect,encode:encode,descriptor:descriptor};
})();

/* Focused naming mode: no coordinate extraction, no font/layout database, no number edits. */
var SCNumberLayer = (function () {
    var STANDARD = "SC_EDITION_NUMBER";
    function get(fn, fallback) {try{return fn();}catch(error){return fallback;}}
    function inside(root, value) {var r=new Folder(root).fsName.toLowerCase().replace(/[\\\/]+$/,""),p=new File(value).fsName.toLowerCase();return p.indexOf(r+"\\")===0||p.indexOf(r+"/")===0;}
    function descriptor(layer) {var r=new ActionReference();r.putIdentifier(charIDToTypeID("Lyr "),layer.id);return executeActionGet(r);}
    function opaque(layer,key) {return get(function(){var d=descriptor(layer),k=stringIDToTypeID(key);return d.hasKey(k)?d.getObjectValue(k).toStream():"";},"UNAVAILABLE");}
    function pattern(text, named) {
        text=String(text||"");
        if(/[\r\n]/.test(text))return null; // Separated numbers require operator review.
        var m=/^\s*((?:(?:LIMITED\s+)?EDITION\s+)?#?\s*)(\d{1,6})(\s*\/\s*|\s+of\s+)(\d{1,6})\s*$/i.exec(text);
        if(m){var n=parseInt(m[2],10),total=parseInt(m[4],10);
            return {text:text,number:n,total:total,number_width:m[2].length,valid:total>0&&n<=total,
                possible_date:!/[#A-Za-z]/.test(m[1])&&n>0&&n<=31&&total<=31};
        }
        if(named&&/^\s*\d{1,6}\s*$/.test(text))return {text:text,number:parseInt(text,10),total:null,number_width:text.replace(/\s/g,"").length,valid:true,possible_date:false};
        return null;
    }
    function explicitlyLocked(layer) {
        if(get(function(){return layer.allLocked;},true)||get(function(){return layer.positionLocked;},false))return true;
        // Text/Smart Object painting getters can be true even with no user-applied lock.
        // Use Photoshop's explicit protection descriptor; never unlock anything.
        return get(function(){
            var d=descriptor(layer),key=stringIDToTypeID("layerLocking");
            if(!d.hasKey(key))return false;
            var locks=d.getObjectValue(key),keys=["protectAll","protectComposite","protectPosition","protectTransparency"];
            for(var i=0;i<keys.length;i++){var k=stringIDToTypeID(keys[i]);if(locks.hasKey(k)&&locks.getBoolean(k))return true;}
            return false;
        },true);
    }
    function childFor(owner,layer,before) {
        var so=get(function(){return descriptor(layer).getObjectValue(stringIDToTypeID("smartObject"));},null);
        if(!so)throw Error("unsupported_smart_object");
        var linked=stringIDToTypeID("linked"),ref=stringIDToTypeID("fileReference");
        if(so.hasKey(linked)&&so.getBoolean(linked))throw Error("linked_smart_object");
        var name=so.hasKey(ref)?so.getString(ref):"";
        if(!/\.(psd|psb)$/i.test(name))throw Error("raster_or_unsupported_smart_object");
        app.activeDocument=owner;owner.activeLayer=layer;
        executeAction(stringIDToTypeID("placedLayerEditContents"),undefined,DialogModes.NO);
        var child=app.activeDocument;
        if(child.id===owner.id||before[String(child.id)])throw Error("smart_object_busy_or_unopened");
        return child;
    }
    function openIds(){var ids={};for(var i=0;i<app.documents.length;i++)ids[String(app.documents[i].id)]=true;return ids;}
    function locate(layers,id){for(var i=0;i<layers.length;i++){var l=layers[i];if(l.id===id)return l;if(l.typename==="LayerSet"){var found=locate(l.layers,id);if(found)return found;}}return null;}
    function scan(doc,request) {
        var out={status:"Needs Review",candidates:[],named:[],warnings:[],complete:true},objects=0;
        function walk(container,owner,path,chain,visible,locked,depth) {
            for(var i=0;i<container.layers.length;i++){
                var l=container.layers[i],current=path.concat([{layer_id:l.id,name:l.name}]);
                var vis=visible&&l.visible,lock=locked||get(function(){return l.allLocked;},true)||get(function(){return l.positionLocked;},false),named=l.name===STANDARD;
                if(l.typename==="LayerSet"){lock=lock||explicitlyLocked(l);if(named)out.named.push({layer_id:l.id,invalid:true,path:current});walk(l,owner,current,chain,vis,lock,depth);continue;}
                if(l.kind===LayerKind.TEXT){
                    var text=get(function(){return l.textItem.contents;},null),p=pattern(text,named);
                    if(p||named)lock=lock||explicitlyLocked(l);
                    var record={layer_id:l.id,path:current,smart_object_chain:chain,name:l.name,text:text,visible:vis,locked:lock,editable:!lock&&text!==null,pattern:p};
                    if(named)out.named.push(record);
                    if(p)out.candidates.push(record);
                    else if(/(?:\d[\s\r\n]*\/[\s\r\n]*\d|EDITION[\s#]*\d)/i.test(String(text||"")))out.warnings.push({code:"unsupported_or_ambiguous_number_text",path:current,text:text});
                    continue;
                }
                if(named)out.named.push({layer_id:l.id,invalid:true,path:current});
                if(l.kind===LayerKind.SMARTOBJECT){
                    lock=lock||explicitlyLocked(l);
                    if(request.skip_smart_objects){out.complete=false;out.warnings.push({code:"previously_unresolved_smart_object",path:current});continue;}
                    var so=get(function(){return descriptor(l).getObjectValue(stringIDToTypeID("smartObject"));},null);
                    var reference=get(function(){return so.getString(stringIDToTypeID("fileReference"));},"");
                    var linked=get(function(){var k=stringIDToTypeID("linked");return so.hasKey(k)&&so.getBoolean(k);},false);
                    if(!so||linked){out.complete=false;out.warnings.push({code:"linked_or_unsupported_smart_object",path:current});continue;}
                    if(!/\.(psd|psb)$/i.test(reference))continue; // Raster objects contain no editable Photoshop text.
                    if(depth>=2||objects>=8){out.complete=false;out.warnings.push({code:"smart_object_limit",path:current});continue;}
                    objects++;var ids=openIds(),child=null,selected=owner.activeLayer;
                    try{child=childFor(owner,l,ids);walk(child,child,current,chain.concat([{layer_id:l.id}]),vis,lock,depth+1);}
                    catch(error){out.complete=false;out.warnings.push({code:"smart_object_unavailable",path:current});}
                    finally{if(child&&!ids[String(child.id)])child.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=owner;owner.activeLayer=selected;}
                }
            }
        }
        walk(doc,doc,[],[],true,false,0);
        if(out.named.length>1){out.reason="multiple_standard_layers";return out;}
        if(out.named.length===1&&(out.named[0].invalid||!out.named[0].pattern)){out.reason="standard_layer_not_valid_editable_number";return out;}
        if(!out.complete||out.warnings.length){out.reason="unsupported_or_incomplete_content";return out;}
        if(out.candidates.length!==1){out.reason=out.candidates.length?"ambiguous_number_layers":"missing_or_flattened_number";return out;}
        var target=out.candidates[0];
        if(!target.visible||target.locked||!target.editable||!target.pattern.valid||target.pattern.possible_date){out.reason="hidden_locked_or_ambiguous_number";return out;}
        if(out.named.length===1&&out.named[0].layer_id!==target.layer_id){out.reason="standard_layer_conflict";return out;}
        out.target=target;out.status=target.name===STANDARD?"Ready":"Can Standardise";out.reason="";return out;
    }
    function surface(doc){
        var rows=[];
        function walk(container,path){for(var i=0;i<container.layers.length;i++){
            var l=container.layers[i],group=l.typename==="LayerSet",row={layer_id:l.id,path_ids:path.concat([l.id]),name:l.name,
                kind:group?"group":String(l.kind),visible:l.visible,locked:get(function(){return l.allLocked;},null),
                opacity:l.opacity,blend_mode:String(l.blendMode),fill_opacity:get(function(){return l.fillOpacity;},null),
                effects_fingerprint:opaque(l,"layerEffects"),geometry_fingerprint:opaque(l,"bounds")};
            if(!group&&l.kind===LayerKind.TEXT){row.text=l.textItem.contents;row.text_state_fingerprint=opaque(l,"textKey");}
            rows.push(row);if(group)walk(l,row.path_ids);
        }}walk(doc,[]);
        return {layers:rows,width:doc.width.as("px"),height:doc.height.as("px"),resolution:doc.resolution,
            mode:String(doc.mode),histogram:get(function(){return doc.histogram;},null)};
    }
    function equal(a,b){return SCPSDInspector.encode(a)===SCPSDInspector.encode(b);}
    function compare(before,after,target,expectedNameChanges){
        if(before.layers.length!==after.layers.length)return {ok:false,reason:"layer_count_changed"};
        var changed=[];
        for(var i=0;i<before.layers.length;i++){
            var a=before.layers[i],b=after.layers[i],ac={},bc={},key;
            if(a.name!==b.name)changed.push({layer_id:a.layer_id,before:a.name,after:b.name});
            for(key in a)if(a.hasOwnProperty(key)&&key!=="name")ac[key]=a[key];
            for(key in b)if(b.hasOwnProperty(key)&&key!=="name")bc[key]=b[key];
            if(!equal(ac,bc))return {ok:false,reason:"non_name_layer_state_changed",layer_id:a.layer_id};
        }
        if(changed.length!==expectedNameChanges)return {ok:false,reason:"unexpected_name_change_count",changes:changed};
        if(expectedNameChanges===1&&(changed[0].layer_id!==target.layer_id||changed[0].after!==STANDARD))return {ok:false,reason:"wrong_layer_renamed"};
        if(before.width!==after.width||before.height!==after.height||before.resolution!==after.resolution||before.mode!==after.mode||!equal(before.histogram,after.histogram))return {ok:false,reason:"document_or_render_histogram_changed"};
        return {ok:true,name_changes:changed,text_styles_effects_geometry_unchanged:true,render_histogram_unchanged:before.histogram!==null&&after.histogram!==null};
    }
    function rename(doc,target){
        var owner=doc,opened=[],childBefore=null,childAfter=null;
        try{
            for(var i=0;i<target.smart_object_chain.length;i++){
                var l=locate(owner.layers,target.smart_object_chain[i].layer_id);
                if(!l)throw Error("target_chain_changed");
                var child=childFor(owner,l,openIds());
                // Never save a linked/external file; embedded content must be in Photoshop's temp folder.
                if(!inside(Folder.temp.fsName,child.fullName.fsName)){child.close(SaveOptions.DONOTSAVECHANGES);throw Error("smart_object_not_temporary");}
                opened.push({doc:child,parent:owner});owner=child;
            }
            var layer=locate(owner.layers,target.layer_id);
            if(!layer||layer.kind!==LayerKind.TEXT||layer.textItem.contents!==target.text||layer.name!==target.name)throw Error("target_identity_changed");
            if(opened.length)childBefore=surface(owner);
            layer.name=STANDARD; // THE ONLY ARTWORK MUTATION IN THIS SCRIPT.
            if(opened.length){childAfter=surface(owner);if(!compare(childBefore,childAfter,target,1).ok)throw Error("child_verification_failed");}
            while(opened.length){var frame=opened.pop();frame.doc.save();frame.doc.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=frame.parent;}
            return {nested:target.smart_object_chain.length>0,child_before:childBefore,child_after:childAfter};
        }finally{while(opened.length){var item=opened.pop();item.doc.close(SaveOptions.DONOTSAVECHANGES);}app.activeDocument=doc;}
    }
    function reopenedChildSurface(doc,target){
        var owner=doc,opened=[];
        try{
            for(var i=0;i<target.smart_object_chain.length;i++){
                var layer=locate(owner.layers,target.smart_object_chain[i].layer_id);
                if(!layer)throw Error("reopened_target_chain_changed");
                var child=childFor(owner,layer,openIds());
                opened.push({doc:child,parent:owner});owner=child;
            }
            return surface(owner);
        }finally{while(opened.length){var frame=opened.pop();frame.doc.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=frame.parent;}app.activeDocument=doc;}
    }
    function run(request){
        if(request.entries.length>10||!inside(request.output_root,request.report_path))throw Error("Unsafe naming request");
        var oldDialogs=app.displayDialogs,oldDoc=app.documents.length?app.activeDocument:null,results=[];
        app.displayDialogs=DialogModes.NO;
        try{for(var i=0;i<request.entries.length;i++){
            var e=request.entries[i],ids=openIds(),doc=null,reopened=null,start=new Date().getTime();
            var result={product_gid:e.product_gid,dropbox_file_id:e.dropbox_file_id,dropbox_revision:e.dropbox_revision};
            if(!inside(request.stage_root,e.work_path)||!/\.psd$/i.test(e.work_path))throw Error("Only disposable PSD copies may be opened");
            try{
                doc=app.open(new File(e.work_path));if(ids[String(doc.id)]){doc=null;throw Error("copy_already_open");}
                var scanRequest={skip_smart_objects:e.skip_smart_objects===true};
                result.detection=scan(doc,scanRequest);
                if(request.mode==="standardise_sample"){
                    var before=surface(doc),target=result.detection.target,renameResult=null;
                    var expected=result.detection.status==="Can Standardise"?1:0;
                    var output=e.work_path;
                    if(expected){
                        if(!e.output_path||!inside(request.output_root,e.output_path)||!/\.psd$/i.test(e.output_path))throw Error("Unsafe sample output");
                        renameResult=rename(doc,target);
                        var options=new PhotoshopSaveOptions();options.layers=true;options.embedColorProfile=true;
                        doc.saveAs(new File(e.output_path),options,true,Extension.LOWERCASE);output=e.output_path;
                    }
                    doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
                    reopened=app.open(new File(output));if(ids[String(reopened.id)]){reopened=null;throw Error("sample_already_open");}
                    var after=surface(reopened);
                    result.verification=compare(before,after,target,renameResult&&renameResult.nested?0:expected);
                    result.reopened=true;result.output_path=output;result.renamed=expected===1;
                    if(result.verification.ok&&renameResult&&renameResult.nested){
                        var childCheck=compare(renameResult.child_before,reopenedChildSurface(reopened,target),target,1);
                        result.verification.child_verification=childCheck;
                        if(!childCheck.ok)result.verification.ok=false;
                    }
                    if(!result.verification.ok)result.detection.status="Needs Review";
                }
            }catch(error){result.error="sample_inspection_or_rename_failed";result.error_number=get(function(){return error.number;},null);if(result.detection)result.detection.status="Needs Review";}
            finally{if(reopened&&!ids[String(reopened.id)])reopened.close(SaveOptions.DONOTSAVECHANGES);if(doc&&!ids[String(doc.id)])doc.close(SaveOptions.DONOTSAVECHANGES);}
            result.elapsed_ms=new Date().getTime()-start;results.push(result);
        }}finally{app.displayDialogs=oldDialogs;if(oldDoc)get(function(){app.activeDocument=oldDoc;},null);}
        var report=new File(request.report_path);report.encoding="UTF8";if(!report.open("w"))throw Error("Naming report cannot be written");
        try{report.write(SCPSDInspector.encode({read_only:request.mode!=="standardise_sample",temporary_copies_only:true,documents:results}));}finally{report.close();}
        return "SC_NUMBER_LAYER_COMPLETE:"+results.length;
    }
    return {run:run,scan:scan,pattern:pattern,compare:compare,proofUtilities:{inside:inside,descriptor:descriptor,opaque:opaque,childFor:childFor,openIds:openIds,locate:locate,surface:surface,explicitlyLocked:explicitlyLocked}};
})();
if(typeof SC_PSD_INSPECT_REQUEST!=="undefined"){
    if(SC_PSD_INSPECT_REQUEST.mode==="standardise_sample"||SC_PSD_INSPECT_REQUEST.mode==="inspect_standardisation")SCNumberLayer.run(SC_PSD_INSPECT_REQUEST);
    else SCPSDInspector.run(SC_PSD_INSPECT_REQUEST);
}



