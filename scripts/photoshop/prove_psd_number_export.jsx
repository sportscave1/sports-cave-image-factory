/* LOCAL NON-PRODUCTION proof. Disposable copies; synthetic or read-only confirmed order units. */
var SCNumberExportProof=(function(){
    function orderNumber(request,entry,target){
        var u=request.confirmed_order_unit;
        if(!u)return request.synthetic_number;
        if(request.entries.length!==1||u.source!=="read_only_supabase"||u.allocation_valid!==true||u.identity_enforced!==true||u.invalidated_at!==null||u.status!=="assigned"||u.quantity!==1||u.unit_ordinal!==1||u.allocation_index!==1)throw Error("order_unit_not_confirmed");
        if(u.shopify_product_gid!==entry.product_gid||u.shopify_order_id!==entry.shopify_order_id||u.shopify_line_item_id!==entry.shopify_line_item_id||u.dropbox_file_id!==entry.dropbox_file_id||u.dropbox_revision!==entry.dropbox_revision||u.content_hash!==entry.content_hash)throw Error("order_file_identity_mismatch");
        var expected=/^#(\d+)\/(\d+)$/.exec(request.expected_display);
        if(!expected||parseInt(expected[1],10)!==u.edition_number||parseInt(expected[2],10)!==u.edition_total||target.pattern.total!==u.edition_total)throw Error("displayed_or_template_edition_mismatch");
        if(!u.allocation_id||!u.allocation_key||u.edition_number!==Math.floor(u.edition_number)||u.edition_number<1||u.edition_number>u.edition_total)throw Error("invalid_assigned_edition");
        return u.edition_number;
    }
    function replacement(text,number){
        if(/[\r\n]/.test(text))throw Error("separated_number_requires_review");
        var m=/^(\s*(?:(?:LIMITED\s+)?EDITION\s+)?(?:No\.\s*)?#?\s*)(\d{1,6})(\s*\/\s*|\s+of\s+)(\d{1,6})(\s*)$/i.exec(text);
        if(!m||number!==Math.floor(number)||number<1||number>parseInt(m[4],10))throw Error("invalid_synthetic_number");
        var digits=String(number);while(digits.length<m[2].length)digits="0"+digits;
        if(digits.length!==m[2].length)throw Error("digit_width_change_requires_review");
        return m[1]+digits+m[3]+m[4]+m[5];
    }
    // Photoshop materialises these paragraph defaults on the first text edit.
    // Canonicalise only observed defaults; preserve all typography/style fields.
    function normaliseTextDefaults(o){
        var defaults={firstLineIndent:0,impliedFirstLineIndent:0,startIndent:0,impliedStartIndent:0,endIndent:0,impliedEndIndent:0,spaceBefore:0,impliedSpaceBefore:0,spaceAfter:0,impliedSpaceAfter:0,autoLeadingPercentage:1.2,leadingType:"leadingBelow",kashidaWidthType:"kashidaWidthMedium",hyphenate:false,justificationWordMinimum:.8,justificationWordDesired:1,justificationWordMaximum:1.33,justificationLetterMinimum:0,justificationLetterDesired:0,justificationLetterMaximum:0,justificationGlyphMinimum:1,justificationGlyphDesired:1,justificationGlyphMaximum:1,hangingRoman:false,burasagari:"burasagariStandard",preferredKinsokuOrder:"pushIn",textEveryLineComposer:true};
        var ranges=o.paragraphStyleRange||[];
        for(var i=0;i<ranges.length;i++){var p=ranges[i].paragraphStyle||{};
            for(var key in defaults)if(defaults.hasOwnProperty(key)&&p.hasOwnProperty(key)){
                var value=p[key],expected=defaults[key];if(value&&typeof value==="object"&&value.unit==="pointsUnit")value=value.value;
                if(value===expected||(typeof value==="number"&&typeof expected==="number"&&Math.abs(value-expected)<.000001))delete p[key];
            }
        }
        var ts=o.textStyleRange||[],td={connectionForms:false,otbaseline:"normal",stylisticSets:0,ornaments:false,markYDistFromBaseline:100,japaneseAlternate:"defaultForm",kashidas:"kashidaDefault",italics:false,gridAlignment:"roman",figureStyle:"normal",diacYOffset:0,mojiZume:0,justificationAlternates:false,diacXOffset:0,kana:false,noBreak:false,proportionalMetrics:false};
        for(var t=0;t<ts.length;t++){var st=ts[t].textStyle||{};for(var tk in td)if(td.hasOwnProperty(tk)&&st.hasOwnProperty(tk)){var tv=st[tk];if(tv&&typeof tv==="object"&&tv.unit==="pointsUnit")tv=tv.value;if(tv===td[tk])delete st[tk];}}
        for(var q=0;q<ranges.length;q++){var ps=ranges[q].paragraphStyle||{};if(ps.listTier===0)delete ps.listTier;if(ps.listStyle&&ps.listStyle.listStylePredefinedTag==="listStylePredefinedTagNone"&&ps.listStyle.bulletListStyleTag==="listStylePredefinedTagNone")delete ps.listStyle;}
        return o;
    }
    function sameTextState(a,b,path){
        path=path||"";if(typeof a!==typeof b)return false;
        if(a===null||b===null||typeof a!=="object"){
            if(a===b)return true;
            // Observed Photoshop float32 round-trip noise; never allow a layout/colour/font change.
            return typeof a==="number"&&typeof b==="number"&&/textStyleRange\/\d+\/textStyle\/(?:size|impliedFontSize)\/value$/.test(path)&&Math.abs(a-b)<=.00001;
        }
        var keys=[],k;for(k in a)if(a.hasOwnProperty(k))keys.push(k);
        var count=0;for(k in b)if(b.hasOwnProperty(k))count++;if(keys.length!==count)return false;
        for(var i=0;i<keys.length;i++){k=keys[i];if(!b.hasOwnProperty(k)||!sameTextState(a[k],b[k],path+"/"+k))return false;}return true;
    }
    function run(request){
        var saved=request;SC_PSD_INSPECT_REQUEST=undefined;
        $.evalFile(new File(request.inspection_script));SC_PSD_INSPECT_REQUEST=saved;
        var u=SCNumberLayer.proofUtilities,enc=SCPSDInspector.encode;
        if(request.non_production!==true||request.entries.length>5||!u.inside(request.output_root,request.report_path))throw Error("unsafe_proof_request");
        var dialogs=app.displayDialogs,oldDoc=app.documents.length?app.activeDocument:null,results=[];
        app.displayDialogs=DialogModes.NO;
        function bounds(layer){var b=layer.bounds;return [b[0].as("px"),b[1].as("px"),b[2].as("px"),b[3].as("px")];}
        function stableText(layer){
            var d=u.descriptor(layer).getObjectValue(stringIDToTypeID("textKey")),keys=["textStyleRange","paragraphStyleRange","textShape","transform","orientation","antiAlias","warp"],o={};
            for(var i=0;i<keys.length;i++){var k=stringIDToTypeID(keys[i]);if(d.hasKey(k))o[keys[i]]=SCPSDInspector.descriptor(d,0)[keys[i]];}
            return normaliseTextDefaults(o);
        }
        function fonts(layer){
            var d=SCPSDInspector.descriptor(u.descriptor(layer).getObjectValue(stringIDToTypeID("textKey")),0),styles=d.textStyleRange||[],found=[];
            for(var i=0;i<styles.length;i++){var name=styles[i].textStyle&&styles[i].textStyle.fontPostScriptName;if(name){app.fonts.getByName(name);found.push(name);}}
            if(!found.length){app.fonts.getByName(layer.textItem.font);found.push(layer.textItem.font);}return found;
        }
        function exportRenders(doc,base){
            if(doc.mode!==DocumentMode.RGB||doc.bitsPerChannel!==BitsPerChannelType.EIGHT)throw Error("export_mode_requires_review_no_conversion");
            var png=new PNGSaveOptions();png.interlaced=false;png.compression=0;
            doc.saveAs(new File(base+".png"),png,true,Extension.LOWERCASE);
            var jpg=new JPEGSaveOptions();jpg.quality=12;jpg.embedColorProfile=true;jpg.formatOptions=FormatOptions.STANDARDBASELINE;jpg.matte=MatteType.WHITE;
            doc.saveAs(new File(base+".jpg"),jpg,true,Extension.LOWERCASE);
        }
        function compareSurface(before,after,targetId,nested){
            if(before.width!==after.width||before.height!==after.height||before.resolution!==after.resolution||before.mode!==after.mode||before.layers.length!==after.layers.length)throw Error("document_structure_changed");
            for(var i=0;i<before.layers.length;i++){
                var a=before.layers[i],b=after.layers[i],ac={},bc={};
                for(var k in a)if(a.hasOwnProperty(k)&&!(a.layer_id===targetId&&!nested&&(k==="text"||k==="text_state_fingerprint"||k==="geometry_fingerprint")))ac[k]=a[k];
                for(var j in b)if(b.hasOwnProperty(j)&&!(b.layer_id===targetId&&!nested&&(j==="text"||j==="text_state_fingerprint"||j==="geometry_fingerprint")))bc[j]=b[j];
                if(enc(ac)!==enc(bc))throw Error("unrelated_layer_state_changed:"+a.layer_id);
            }
        }
        function openTarget(doc,target){
            var owner=doc,frames=[];
            for(var i=0;i<target.smart_object_chain.length;i++){
                var l=u.locate(owner.layers,target.smart_object_chain[i].layer_id),child=u.childFor(owner,l,u.openIds());
                if(!u.inside(Folder.temp.fsName,child.fullName.fsName)){child.close(SaveOptions.DONOTSAVECHANGES);throw Error("embedded_child_not_temporary");}
                frames.push({doc:child,parent:owner,layer:l});owner=child;
            }
            return {owner:owner,frames:frames,layer:u.locate(owner.layers,target.layer_id)};
        }
        function closeFrames(opened,save){while(opened.frames.length){var f=opened.frames.pop();if(save)f.doc.save();f.doc.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=f.parent;}}
        function badgeProbe(doc){
            var findings=[];
            function walk(container){for(var i=0;i<container.layers.length;i++){var l=container.layers[i];if(l.typename==="LayerSet"){walk(l);continue;}if(l.kind!==LayerKind.SMARTOBJECT||!/plaque|badge/i.test(l.name))continue;
                var child=null;try{child=u.childFor(doc,l,u.openIds());var texts=[],kinds={};function inspect(c){for(var j=0;j<c.layers.length;j++){var x=c.layers[j];if(x.typename==="LayerSet"){inspect(x);continue;}var key=String(x.kind);kinds[key]=(kinds[key]||0)+1;if(x.kind===LayerKind.TEXT)texts.push({id:x.id,name:x.name,text:x.textItem.contents});}}inspect(child);findings.push({layer_id:l.id,name:l.name,embedded:true,width:child.width.as("px"),height:child.height.as("px"),texts:texts,kinds:kinds});}
                catch(error){findings.push({layer_id:l.id,name:l.name,blocked:String(error.message)});}finally{if(child)child.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=doc;}
            }}walk(doc);return findings;
        }
        try{for(var i=0;i<request.entries.length;i++){
            var e=request.entries[i],doc=null,reopened=null,opened=null,ids=u.openIds(),start=new Date().getTime(),r={product_title:e.product_title,product_gid:e.product_gid,dropbox_file_id:e.dropbox_file_id,dropbox_revision:e.dropbox_revision,non_production:true};
            try{
                if(!u.inside(request.stage_root,e.work_path)||!u.inside(request.output_root,e.output_prefix)||!/NON_PRODUCTION/.test(e.output_prefix))throw Error("unsafe_copy_or_output");
                doc=app.open(new File(e.work_path));if(ids[String(doc.id)]){doc=null;throw Error("copy_already_open");}
                r.badge_objects=badgeProbe(doc);
                var target=e.target;if(!target||!target.visible||target.locked||!target.editable||!target.pattern||!target.pattern.valid||target.pattern.possible_date)throw Error("no_verified_target_manual_preparation_required");
                opened=openTarget(doc,target);var layer=opened.layer;
                if(!layer||layer.kind!==LayerKind.TEXT||!layer.visible||u.explicitlyLocked(layer)||layer.textItem.contents!==target.text||layer.name!==target.name)throw Error("target_not_verified_editable");
                r.fonts=fonts(layer);r.before_text=layer.textItem.contents;r.after_text=replacement(r.before_text,orderNumber(request,e,target));
                if(request.confirmed_order_unit)r.order_unit=request.confirmed_order_unit;
                var textState=stableText(layer),beforeBounds=bounds(layer),childBefore=u.surface(opened.owner),rootBefore=u.surface(doc);
                // Nested mapping must be independently proven before visual-region validation can accept it.
                if(opened.frames.length)throw Error("nested_target_region_transform_not_yet_proven");
                exportRenders(doc,e.output_prefix+"-BEFORE");
                var text=u.descriptor(layer).getObjectValue(stringIDToTypeID("textKey"));text.putString(stringIDToTypeID("textKey"),r.after_text);
                var ref=new ActionReference();ref.putIdentifier(charIDToTypeID("Lyr "),layer.id);var change=new ActionDescriptor();change.putReference(charIDToTypeID("null"),ref);change.putObject(charIDToTypeID("T   "),charIDToTypeID("TxLr"),text);executeAction(charIDToTypeID("setd"),change,DialogModes.NO);
                r.actual_text=layer.textItem.contents;r.text_state_before=textState;r.text_state_after=stableText(layer);
                if(layer.name!==target.name)layer.name=target.name;
                if(layer.textItem.contents!==r.after_text||!sameTextState(r.text_state_after,textState))throw Error("text_or_format_verification_failed");
                r.number_bounds_before=beforeBounds;r.number_bounds_after=bounds(layer);
                compareSurface(childBefore,u.surface(opened.owner),layer.id,false);
                closeFrames(opened,true);opened=null;
                var psd=new PhotoshopSaveOptions();psd.layers=true;psd.embedColorProfile=true;doc.saveAs(new File(e.output_prefix+".psd"),psd,true,Extension.LOWERCASE);doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
                reopened=app.open(new File(e.output_prefix+".psd"));if(ids[String(reopened.id)]){reopened=null;throw Error("output_already_open");}
                opened=openTarget(reopened,target);layer=opened.layer;
                if(layer.textItem.contents!==r.after_text||!sameTextState(stableText(layer),textState))throw Error("reopened_text_or_format_changed");
                compareSurface(rootBefore,u.surface(reopened),layer.id,false);r.width=reopened.width.as("px");r.height=reopened.height.as("px");r.resolution=reopened.resolution;
                closeFrames(opened,false);opened=null;exportRenders(reopened,e.output_prefix+"-AFTER");
                var jpgIds=u.openIds(),jpgDoc=app.open(new File(e.output_prefix+"-AFTER.jpg"));
                if(jpgIds[String(jpgDoc.id)])throw Error("jpg_output_already_open");
                try{r.native_jpg_reopen={width:jpgDoc.width.as("px"),height:jpgDoc.height.as("px"),resolution:jpgDoc.resolution,profile:jpgDoc.colorProfileName};
                    if(r.native_jpg_reopen.width!==r.width||r.native_jpg_reopen.height!==r.height||r.native_jpg_reopen.resolution!==r.resolution||r.native_jpg_reopen.profile!==reopened.colorProfileName)throw Error("jpg_metadata_changed");
                }finally{jpgDoc.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=reopened;}
                r.psd=e.output_prefix+".psd";r.before_png=e.output_prefix+"-BEFORE.png";r.after_png=e.output_prefix+"-AFTER.png";r.before_jpg=e.output_prefix+"-BEFORE.jpg";r.after_jpg=e.output_prefix+"-AFTER.jpg";r.reopened=true;r.structural_verification=true;r.status="Awaiting strict pixel verification";
            }catch(error){r.status="Blocked";r.error=String(error.message);}
            finally{if(opened)closeFrames(opened,false);if(reopened&&!ids[String(reopened.id)])reopened.close(SaveOptions.DONOTSAVECHANGES);if(doc&&!ids[String(doc.id)])doc.close(SaveOptions.DONOTSAVECHANGES);}
            r.elapsed_ms=new Date().getTime()-start;results.push(r);
        }}finally{app.displayDialogs=dialogs;if(oldDoc)try{app.activeDocument=oldDoc;}catch(ignore){}}
        var report=new File(request.report_path);report.encoding="UTF8";if(!report.open("w"))throw Error("proof_report_failed");try{report.write(enc({non_production:true,documents:results}));}finally{report.close();}
        return "SC_NUMBER_EXPORT_PROOF_COMPLETE:"+results.length;
    }
    return {replacement:replacement,orderNumber:orderNumber,normaliseTextDefaults:normaliseTextDefaults,sameTextState:sameTextState,run:run};
})();
if(typeof SC_PSD_INSPECT_REQUEST!=="undefined")SCNumberExportProof.run(SC_PSD_INSPECT_REQUEST);
