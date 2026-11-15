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
