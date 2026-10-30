/* One-time preparation, disposable staged input only. Never saves a PSD.
   A lossless master plus small opaque number patches retains Photoshop's exact
   font, antialiasing, effects and individual position. No per-order Photoshop. */
var SCAutoEditionsPreparation = (function () {
    function witnessICC(data) {
        function uint(p) {
            if (p+4>data.length) throw Error("profile_inspector_failure");
            return data.charCodeAt(p)*16777216+data.charCodeAt(p+1)*65536+data.charCodeAt(p+2)*256+data.charCodeAt(p+3);
        }
        if (data.substr(0,6)!=="8BPS\x00\x01") throw Error("profile_inspector_failure");
        var start=30+uint(26),size=uint(start),pos=start+4,end=pos+size,icc=null;
        if (size>4194304 || end>data.length) throw Error("profile_inspector_failure");
        while(pos<end){
            if(data.substr(pos,4)!=="8BIM") throw Error("profile_inspector_failure");
            var id=data.charCodeAt(pos+4)*256+data.charCodeAt(pos+5),name=data.charCodeAt(pos+6)+1;
            pos+=6+name+(name%2);var length=uint(pos);pos+=4;
            if(pos+length+(length%2)>end) throw Error("profile_inspector_failure");
            if(id===1039){if(icc!==null) throw Error("profile_inspector_failure");icc=data.substr(pos,length);}
            pos+=length+(length%2);
        }
        if(!icc) throw Error("profile_inspector_failure");return icc;
    }
    function binary(path) {
        var file=new File(path);file.encoding="BINARY";
        if(file.length>4194304 || !file.open("r")) throw Error("profile_inspector_failure");
        try{return file.read();}finally{file.close();}
    }
    function profileWitness(doc, root, expectedICC) {
        // A tiny disposable PSD provides the actual Photoshop ICC bytes. Names
        // alone cannot distinguish two installed profiles with the same label.
        var witness = doc.duplicate("icc-evidence", true);
        try {
            witness.crop([UnitValue(0,"px"),UnitValue(0,"px"),UnitValue(1,"px"),UnitValue(1,"px")]);
            var options = new PhotoshopSaveOptions();options.layers=false;options.embedColorProfile=true;
            witness.saveAs(new File(root + "/profile-witness.psd"),options,true,Extension.LOWERCASE);
            if(expectedICC && witnessICC(binary(root+"/profile-witness.psd"))!==binary(expectedICC))
                throw Error("export_profile_changed");
        } finally { witness.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=doc; }
    }
    function inside(root, path) {
        var base = new Folder(root).fsName.toLowerCase().replace(/[\\\/]+$/, "");
        var target = new File(path).fsName.toLowerCase();
        return target.indexOf(base + "\\") === 0 || target.indexOf(base + "/") === 0;
    }
    function run(r) {
        if (!r || !inside(r.stage_root, r.input) || !inside(r.output_root, r.report)
            || !r.icc_path || !inside(r.stage_root,r.icc_path)
            || !/\.psd$/i.test(r.input) || !/\.json$/i.test(r.report)
            || !r.number_layer_name || !r.plaque_layer_name) throw Error("unsafe_preparation_request");
        var strategy = r.export_strategy || "duplicate_merged";
        if (strategy !== "duplicate_merged" && strategy !== "history_merged_crop") throw Error("unsupported_export_strategy");
        // The Python caller selects history export only with measured memory
        // headroom. Both paths retain all independent references and proofs.
        var original = app.documents.length ? app.activeDocument : null, doc = null;
        var dialogs = app.displayDialogs, existing = {}, layer = null, plaque = null, exportProfiles = {};
        for (var e = 0; e < app.documents.length; e++) existing[String(app.documents[e].id)] = true;
        app.displayDialogs = DialogModes.NO;
        function named(container, name, found) {
            for (var i = 0; i < container.layers.length; i++) {
                var l = container.layers[i];
                if (l.name === name) found.push(l);
                if (l.typename === "LayerSet") named(l, name, found);
            }
        }
        function box(l) {
            var b = l.bounds;
            return [b[0].as("px"), b[1].as("px"), b[2].as("px"), b[3].as("px")];
        }
        var timings = {export_strategy:strategy,photoshop_version:String(app.version || "unknown"),number_samples:[],completed_number_count:0}, nativeStarted = new Date().getTime(), completed = false;
        function timed(key, fn) {
            var started = new Date().getTime();
            try { return fn(); } finally { timings[key] = (timings[key] || 0) + new Date().getTime()-started; }
        }
        function savePNG(d, name) {
            var destination = r.output_root + "/" + name;
            if (!inside(r.output_root, destination)) throw Error("unsafe_output");
            var options = new PNGSaveOptions(); options.interlaced = false; options.compression = 6;
            var profile;
            try {
                if (d.colorProfileType === ColorProfile.NONE) throw Error("source_profile_requires_review");
                profile = d.colorProfileName;
            } catch (profileError) { throw Error("source_profile_requires_review"); }
            if (!profile) throw Error("source_profile_requires_review");
            timed("png_save_ms",function(){d.saveAs(new File(destination), options, true, Extension.LOWERCASE);});
            if (d.colorProfileName !== profile) throw Error("export_profile_changed");
            exportProfiles[name] = profile;
        }
        function write(value) {
            var f = new File(r.report); f.encoding = "UTF8";
            if (!f.open("w")) throw Error("report_unavailable");
            try { f.write(SCPSDInspector.encode(value)); } finally { f.close(); }
        }
        try {
            var tick = new Date().getTime();
            app.bringToFront(); // A minimized Photoshop can reject native PSD opens.
            doc = app.open(new File(r.input));
            timings.photoshop_open_ms = new Date().getTime()-tick; tick = new Date().getTime();
            if (existing[String(doc.id)]) { doc = null; throw Error("staged_document_already_open"); }
            if (doc.mode !== DocumentMode.RGB || doc.bitsPerChannel !== BitsPerChannelType.EIGHT)
                throw Error("colour_conversion_requires_approval");
            var numbers = [], plaques = [];
            named(doc, r.number_layer_name, numbers); named(doc, r.plaque_layer_name, plaques);
            if (numbers.length !== 1 || plaques.length !== 1) throw Error("ambiguous_roles");
            layer = numbers[0]; plaque = plaques[0];
            if (layer.kind !== LayerKind.TEXT || !layer.visible || layer.allLocked || !plaque.visible)
                throw Error("uneditable_or_hidden_role");
            if (layer.parent !== doc || plaque.parent !== doc)
                throw Error("nested_roles_require_transform_review");
            var inspection = timed("psd_inspection_ms",function(){return SCPSDInspector.inspect(doc, {smart_object_depth:0,smart_object_limit:0});});
            if (inspection.document.profile_state !== "tagged") throw Error("profile_inspector_failure");
            timed("icc_witness_ms",function(){profileWitness(doc,r.output_root,r.icc_path);});
            var sourceDimensions = [doc.width.as("px"), doc.height.as("px")];
            var hidden = null, approvedHidden = r.approved_hidden_number;
            if (approvedHidden) {
                var hiddenMatches=[];named(doc,approvedHidden.name,hiddenMatches);
                if(hiddenMatches.length!==1)throw Error("approved_hidden_number_changed");
                hidden=hiddenMatches[0];
                if(hidden.id!==approvedHidden.layer_id || hidden.kind!==LayerKind.TEXT || hidden.parent!==doc
                    || !hidden.visible || SCPSDInspector.encode(box(hidden))!==SCPSDInspector.encode(approvedHidden.bounds_px))
                    throw Error("approved_hidden_number_changed");
            }
            var sourcePlaqueBounds = box(plaque), scale = r.scale || 1;
            if (r.preflight_only === true) {
                savePNG(doc,"preflight-original.png");
                var bottom = null, visibility = [];
                for (var v=0;v<doc.layers.length;v++) {
                    visibility.push(doc.layers[v].visible);
                    // The exact reviewed obsolete number is removed on the staged copy.
                    // It cannot be an artwork/background candidate. All pixel proofs still apply.
                    if(doc.layers[v].visible && doc.layers[v]!==hidden)bottom=doc.layers[v];
                }
                var candidate = null;
                if(scale!==1 && bottom && bottom!==layer && bottom!==plaque && bottom.typename==="ArtLayer" && !bottom.isBackgroundLayer) {
                    candidate={layer_id:bottom.id,name:bottom.name};
                    try {
                        for(var hide=0;hide<doc.layers.length;hide++)if(doc.layers[hide]!==bottom)doc.layers[hide].visible=false;
                        savePNG(doc,"preflight-artwork.png");
                    } finally {
                        for(var restore=0;restore<doc.layers.length;restore++)doc.layers[restore].visible=visibility[restore];
                    }
                }
                write({inspection:inspection,resize_background:candidate});
                completed=true;
                return "AUTO_EDITIONS_PREFLIGHT";
            }
            if(r.opaque_resize_layer) {
                var bg=[], approved=r.opaque_resize_layer;
                named(doc,approved.name,bg);
                if(bg.length!==1 || bg[0].id!==approved.layer_id || bg[0]===layer || bg[0]===plaque || !bg[0].visible)
                    throw Error("resize_background_identity_changed");
                // Only Python-verified opaque native pixels, on the disposable
                // staged document. No fill colour and no source PSD writes.
                // Photoshop's background setter also reveals the active layer.
                // A saved hidden selection may contain obsolete artwork; select
                // only the verified visible candidate before this operation.
                doc.activeLayer=bg[0];
                if(bg[0].kind===LayerKind.SMARTOBJECT)bg[0].rasterize(RasterizeType.ENTIRELAYER);
                bg[0].isBackgroundLayer=true;
                savePNG(doc,"resize-original.png");
            }
            timings.layer_inspection_ms = new Date().getTime()-tick; tick = new Date().getTime();
            var target = r.target_dimensions || [sourceDimensions[0]*scale,sourceDimensions[1]*scale];
            if (!r.preparation_plan && scale !== 1 && scale !== 2 && scale !== 3 && scale !== 4) throw Error("unsupported_preparation_scale");
            if (target.length!==2 || target[0]!==Math.floor(target[0]) || target[1]!==Math.floor(target[1])
                || target[0]<sourceDimensions[0] || target[1]<sourceDimensions[1]
                || target[1]!==Math.floor(sourceDimensions[1]*target[0]/sourceDimensions[0]+0.5))
                throw Error("nonproportional_preparation_target");
            if (target[0]*target[1] > 95000000)
                throw Error("canvas_exceeds_worker_limit");
            // Resize the layered staged document, never the source or another template.
            // Photoshop rerenders editable text/shapes; raster layers use bicubic smoother.
            if (scale !== 1) timed("layered_resize_ms",function(){doc.resizeImage(UnitValue(target[0],"px"),
                r.preparation_plan && scale!==Math.floor(scale) ? null : UnitValue(target[1],"px"), null, ResampleMethod.BICUBICSMOOTHER);});
            if(doc.width.as("px")!==target[0] || doc.height.as("px")!==target[1])throw Error("preparation_target_rounding_changed");
            // Keep the untouched composite as an independent outside-number proof.
            if(hidden){savePNG(doc,"uncorrected.png");hidden.visible=false;}
            timed("original_export_ms",function(){savePNG(doc, "original.png");});
            app.fonts.getByName(layer.textItem.font);
            var text = layer.textItem.contents;
            var m = /^(\s*(?:(?:LIMITED\s+)?EDITION\s+)?(?:No\.\s*)?#?\s*)(\d{1,6})(\s*\/\s*|\s+of\s+)(\d{1,6})(\s*)$/i.exec(text);
            if (!m || parseInt(m[4], 10) !== r.edition_total || r.edition_total < 1 || r.edition_total > 1000)
                throw Error("edition_total_mismatch");
            var total = r.edition_total, w = doc.width.as("px"), h = doc.height.as("px");
            if (w * h > 110000000) throw Error("canvas_exceeds_worker_limit");
            var originalBounds = box(layer), plaqueBounds = box(plaque), region = originalBounds.slice(0);
            function replace(n) {
                var digits = String(n); while (digits.length < m[2].length) digits = "0" + digits;
                if (digits.length !== m[2].length) throw Error("number_width_requires_review");
                timed("number_text_update_ms",function(){layer.textItem.contents = m[1] + digits + m[3] + m[4] + m[5];});
            }
            // Measure every actual rendering; no assumed template badge position.
            var scanStarted = new Date().getTime();
            for (var n = 1; n <= total; n++) {
                replace(n); var b = box(layer);
                region[0] = Math.min(region[0], b[0]); region[1] = Math.min(region[1], b[1]);
                region[2] = Math.max(region[2], b[2]); region[3] = Math.max(region[3], b[3]);
            }
            timings.number_bounds_scan_ms = new Date().getTime()-scanStarted;
            region = [Math.floor(region[0])-4, Math.floor(region[1])-4, Math.ceil(region[2])+4, Math.ceil(region[3])+4];
            if (region[0] < 0 || region[1] < 0 || region[2] > w || region[3] > h
                || region[0] < plaqueBounds[0] || region[1] < plaqueBounds[1]
                || region[2] > plaqueBounds[2] || region[3] > plaqueBounds[3]
                || (region[2]-region[0])*(region[3]-region[1]) > w*h/10)
                throw Error("number_region_requires_review");
            layer.visible = false; timed("master_export_ms",function(){savePNG(doc, "master.png");}); layer.visible = true;
            timings.master_preparation_ms = new Date().getTime()-tick; tick = new Date().getTime();
            for (var number = 1; number <= total; number++) {
                var numberStarted = new Date().getTime();
                replace(number);
                if (number === 1 || number === r.reference_number || number === total)
                    timed("reference_export_ms",function(){savePNG(doc, "reference-" + number + ".png");});
                function crop(d) { timed("patch_crop_ms",function(){d.crop([UnitValue(region[0],"px"),UnitValue(region[1],"px"),UnitValue(region[2],"px"),UnitValue(region[3],"px")]);}); }
                if (strategy === "duplicate_merged") {
                    var patch = timed("patch_duplicate_ms",function(){return doc.duplicate("edition-patch", true);});
                    try {
                        crop(patch);
                        timed("patch_save_ms",function(){savePNG(patch, "number-" + number + ".png");});
                    } finally { timed("patch_close_ms",function(){patch.close(SaveOptions.DONOTSAVECHANGES);}); app.activeDocument = doc; }
                } else {
                    // Merge the FULL composite before cropping,
                    // then restore the exact layered history state. Cropping a
                    // layered document directly can change canvas-relative FX.
                    // Every patch must match the legacy output in native trials.
                    var anchor = doc.activeHistoryState, numberLayerId = layer.id;
                    try {
                        timed("patch_merge_ms",function(){doc.mergeVisibleLayers();});
                        crop(doc);
                        timed("patch_save_ms",function(){savePNG(doc, "number-" + number + ".png");});
                    } finally {
                        timed("history_restore_ms",function(){doc.activeHistoryState = anchor;});
                        // Photoshop can rename an uncustomised text layer when
                        // its contents change. Restore by the exact layer ID,
                        // never the original display name or a guessed role.
                        var restored = [];
                        for (var ri=0;ri<doc.layers.length;ri++)
                            if(doc.layers[ri].id===numberLayerId)restored.push(doc.layers[ri]);
                        if (restored.length !== 1 || restored[0].kind !== LayerKind.TEXT || restored[0].parent !== doc)
                            throw Error("preparation_history_restore_failed");
                        layer = restored[0];
                        if (doc.width.as("px") !== w || doc.height.as("px") !== h)
                            throw Error("preparation_history_restore_failed");
                    }
                }
                timings.number_samples.push({number:number,total_ms:new Date().getTime()-numberStarted});
                timings.completed_number_count=number;
            }
            timings.numbering_assets_ms = new Date().getTime()-tick;
            var geometry={scale:scale,method:scale===1?"native":"photoshop_layered_bicubic_smoother",
                    supplier_verified:false,aspect_preserved:true,quality_approval_required:scale!==1};
            if(r.preparation_plan)geometry.plan=r.preparation_plan;
            write({timings:timings,dimensions:[w,h],source_dimensions:sourceDimensions,upscaled:scale!==1,
                preparation_geometry:geometry,
                source_plaque_bounds:sourcePlaqueBounds,
                edition_total:total,number_region:region,original_number_bounds:originalBounds,
                plaque_bounds:plaqueBounds,original_text:text,number_layer_name:r.number_layer_name,
                plaque_layer_name:r.plaque_layer_name,font:layer.textItem.font,
                resolution:doc.resolution,source_modified:false,print_ready:false,
                source_inspection:inspection,export_profiles:exportProfiles});
            completed = true;
            return "AUTO_EDITIONS_PREPARED:" + total;
        } finally {
            var closed = !doc, closeStarted = new Date().getTime();
            try {
                if (doc && !existing[String(doc.id)]) { doc.close(SaveOptions.DONOTSAVECHANGES); closed = true; }
            } finally {
                // Any leftover witness/patch document makes cleanup uncertain.
                for (var remaining = 0; remaining < app.documents.length; remaining++)
                    if (!existing[String(app.documents[remaining].id)]) closed = false;
                timings.staged_document_close_ms = new Date().getTime()-closeStarted;
                timings.native_total_ms = new Date().getTime()-nativeStarted;
                app.displayDialogs = dialogs;
                if (original) try { app.activeDocument = original; } catch (ignored) {}
                // Separate diagnostic sidecar: never changes manifest identity.
                var status = new File(r.output_root + "/native-status.json");status.encoding="UTF8";
                if (!status.open("w")) throw Error("native_cleanup_report_unavailable");
                try {if (!status.write(SCPSDInspector.encode({completed:completed,owned_document_closed:closed,timings:timings}))) throw Error("native_cleanup_report_unavailable");} finally {status.close();}
            }
        }
    }
    return {run:run,profileWitness:profileWitness,witnessICC:witnessICC};
})();
if (typeof SC_AUTO_EDITIONS_REQUEST !== "undefined") SCAutoEditionsPreparation.run(SC_AUTO_EDITIONS_REQUEST);
