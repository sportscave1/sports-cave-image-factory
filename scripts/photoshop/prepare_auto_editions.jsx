/* One-time preparation, disposable staged input only. Never saves a PSD.
   A lossless master plus small opaque number patches retains Photoshop's exact
   font, antialiasing, effects and individual position. No per-order Photoshop. */
var SCAutoEditionsPreparation = (function () {
    function inside(root, path) {
        var base = new Folder(root).fsName.toLowerCase().replace(/[\\\/]+$/, "");
        var target = new File(path).fsName.toLowerCase();
        return target.indexOf(base + "\\") === 0 || target.indexOf(base + "/") === 0;
    }
    function run(r) {
        if (!r || !inside(r.stage_root, r.input) || !inside(r.output_root, r.report)
            || !/\.psd$/i.test(r.input) || !/\.json$/i.test(r.report)
            || !r.number_layer_name || !r.plaque_layer_name) throw Error("unsafe_preparation_request");
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
        function savePNG(d, name) {
            var destination = r.output_root + "/" + name;
            if (!inside(r.output_root, destination)) throw Error("unsafe_output");
            var options = new PNGSaveOptions(); options.interlaced = false; options.compression = 6;
            var profile = d.colorProfileName;
            d.saveAs(new File(destination), options, true, Extension.LOWERCASE);
            if (d.colorProfileName !== profile) throw Error("export_profile_changed");
            exportProfiles[name] = profile;
        }
        function write(value) {
            var f = new File(r.report); f.encoding = "UTF8";
            if (!f.open("w")) throw Error("report_unavailable");
            try { f.write(SCPSDInspector.encode(value)); } finally { f.close(); }
        }
        try {
            var tick = new Date().getTime(), timings = {};
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
            var inspection = SCPSDInspector.inspect(doc, {smart_object_depth:0,smart_object_limit:0});
            var sourceDimensions = [doc.width.as("px"), doc.height.as("px")];
            var sourcePlaqueBounds = box(plaque), scale = r.scale || 1;
            timings.layer_inspection_ms = new Date().getTime()-tick; tick = new Date().getTime();
            if (scale !== 1 && scale !== 2 && scale !== 3 && scale !== 4) throw Error("unsupported_preparation_scale");
            if (sourceDimensions[0]*sourceDimensions[1]*scale*scale > 95000000)
                throw Error("canvas_exceeds_worker_limit");
            // Resize the layered staged document, never the source or another template.
            // Photoshop rerenders editable text/shapes; raster layers use bicubic smoother.
            if (scale !== 1) doc.resizeImage(UnitValue(sourceDimensions[0]*scale,"px"),
                UnitValue(sourceDimensions[1]*scale,"px"), null, ResampleMethod.BICUBICSMOOTHER);
            // Keep the untouched composite as an independent outside-number proof.
            savePNG(doc, "original.png");
            app.fonts.getByName(layer.textItem.font);
            var text = layer.textItem.contents;
            var m = /^(\s*(?:(?:LIMITED\s+)?EDITION\s+)?#?\s*)(\d{1,6})(\s*\/\s*|\s+of\s+)(\d{1,6})(\s*)$/i.exec(text);
            if (!m || parseInt(m[4], 10) !== r.edition_total || r.edition_total < 1 || r.edition_total > 1000)
                throw Error("edition_total_mismatch");
            var total = r.edition_total, w = doc.width.as("px"), h = doc.height.as("px");
            if (w * h > 110000000) throw Error("canvas_exceeds_worker_limit");
            var originalBounds = box(layer), plaqueBounds = box(plaque), region = originalBounds.slice(0);
            function replace(n) {
                var digits = String(n); while (digits.length < m[2].length) digits = "0" + digits;
                if (digits.length !== m[2].length) throw Error("number_width_requires_review");
                layer.textItem.contents = m[1] + digits + m[3] + m[4] + m[5];
            }
            // Measure every actual rendering; no assumed template badge position.
            for (var n = 1; n <= total; n++) {
                replace(n); var b = box(layer);
                region[0] = Math.min(region[0], b[0]); region[1] = Math.min(region[1], b[1]);
                region[2] = Math.max(region[2], b[2]); region[3] = Math.max(region[3], b[3]);
            }
            region = [Math.floor(region[0])-4, Math.floor(region[1])-4, Math.ceil(region[2])+4, Math.ceil(region[3])+4];
            if (region[0] < 0 || region[1] < 0 || region[2] > w || region[3] > h
                || region[0] < plaqueBounds[0] || region[1] < plaqueBounds[1]
                || region[2] > plaqueBounds[2] || region[3] > plaqueBounds[3]
                || (region[2]-region[0])*(region[3]-region[1]) > w*h/10)
                throw Error("number_region_requires_review");
            layer.visible = false; savePNG(doc, "master.png"); layer.visible = true;
            timings.master_preparation_ms = new Date().getTime()-tick; tick = new Date().getTime();
            for (var number = 1; number <= total; number++) {
                replace(number);
                if (number === 1 || number === r.reference_number || number === total)
                    savePNG(doc, "reference-" + number + ".png");
                var patch = doc.duplicate("edition-patch", true);
                try {
                    patch.crop([UnitValue(region[0],"px"),UnitValue(region[1],"px"),UnitValue(region[2],"px"),UnitValue(region[3],"px")]);
                    savePNG(patch, "number-" + number + ".png");
                } finally { patch.close(SaveOptions.DONOTSAVECHANGES); app.activeDocument = doc; }
            }
            timings.numbering_assets_ms = new Date().getTime()-tick;
            write({timings:timings,dimensions:[w,h],source_dimensions:sourceDimensions,upscaled:scale!==1,
                preparation_geometry:{scale:scale,method:scale===1?"native":"photoshop_layered_bicubic_smoother",
                    supplier_verified:false,aspect_preserved:true,quality_approval_required:scale!==1},
                source_plaque_bounds:sourcePlaqueBounds,
                edition_total:total,number_region:region,original_number_bounds:originalBounds,
                plaque_bounds:plaqueBounds,original_text:text,number_layer_name:r.number_layer_name,
                plaque_layer_name:r.plaque_layer_name,font:layer.textItem.font,
                resolution:doc.resolution,source_modified:false,print_ready:false,
                source_inspection:inspection,export_profiles:exportProfiles});
            return "AUTO_EDITIONS_PREPARED:" + total;
        } finally {
            if (doc && !existing[String(doc.id)]) doc.close(SaveOptions.DONOTSAVECHANGES);
            app.displayDialogs = dialogs;
            if (original) try { app.activeDocument = original; } catch (ignored) {}
        }
    }
    return {run:run};
})();
if (typeof SC_AUTO_EDITIONS_REQUEST !== "undefined") SCAutoEditionsPreparation.run(SC_AUTO_EDITIONS_REQUEST);
