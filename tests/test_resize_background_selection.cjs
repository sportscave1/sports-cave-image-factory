// Reproduce Photoshop's demonstrated active-hidden-layer side effect in the
// actual shared native block. No product names or identity exceptions.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('scripts/photoshop/prepare_auto_editions.jsx','utf8');
const block=source.slice(source.indexOf('if(r.opaque_resize_layer) {'),source.indexOf('timings.layer_inspection_ms'));
for(const smart of [true,false]){
 const obsolete={id:70,visible:false},plaque={id:3,visible:true},number={id:2,visible:true};
 const doc={activeLayer:obsolete};
 const bg={id:9,name:'Synthetic opaque artwork',visible:true,kind:smart?'smart':'raster',rasterize(){this.kind='raster'}};
 Object.defineProperty(bg,'isBackgroundLayer',{set(){doc.activeLayer.visible=true;this.id=1}});
 let saved=0;
 vm.runInNewContext(block,{r:{opaque_resize_layer:{name:bg.name,layer_id:9}},doc,layer:number,plaque,
   named:(d,name,rows)=>rows.push(bg),LayerKind:{SMARTOBJECT:'smart'},RasterizeType:{ENTIRELAYER:1},
   savePNG:()=>{saved++;assert.equal(obsolete.visible,false);assert.equal(doc.activeLayer,bg)}});
 assert.equal(saved,1);assert.equal(number.visible,true);assert.equal(plaque.visible,true);
}
console.log('Native background selection: hidden selected raster/smart-object cases passed');
for(const [file,opening] of [['scripts/photoshop/inspect_psd_editions.jsx','doc=app.open(new File(e.work_path));'],
 ['scripts/photoshop/prepare_auto_editions.jsx','doc = app.open(new File(r.input));']]){
 const text=fs.readFileSync(file,'utf8'),end=text.indexOf(opening)+opening.length;
 const start=text.lastIndexOf('app.bringToFront();',end);
 assert.ok(start>=0);
 let minimized=true,opened=0;
 vm.runInNewContext(text.slice(start,end),{app:{bringToFront(){minimized=false},open(){assert.equal(minimized,false);opened++;return {}}},
   File:function(path){this.path=path},e:{work_path:'staged.psd'},r:{input:'staged.psd'}});
 assert.equal(opened,1);
}
console.log('Native PSD opens restore minimized Photoshop before opening staged copies');

const canvasPixels = source.slice(source.indexOf('    function canvasPixels('), source.indexOf('    function run(r)'));
const pixelCount = vm.runInNewContext(canvasPixels + 'canvasPixels');
assert.equal(pixelCount({as: () => 7015.999999999999}), 7016);
assert.equal(pixelCount({as: () => 4961.000000000001}), 4961);
assert.throws(() => pixelCount({as: () => 7016.25}), /nonintegral_preparation_canvas/);
const pattern = vm.runInNewContext(source.match(/var m = (\/\^.+\/i)\.exec\(text\);/)[1]);
const editionText = pattern.exec('#047/100\rLIMITED EDTION');
assert.equal(editionText[1] + '083' + editionText[3] + editionText[4] + editionText[5], '#083/100\rLIMITED EDTION');
assert.equal(pattern.test('#047/100\rPLAYER 23'), false);
console.log('Native canvas precision and two-line edition text checks passed');
