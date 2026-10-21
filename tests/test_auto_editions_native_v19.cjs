// Instrumented ExtendScript control-flow model. NOT a Photoshop speed/pixel benchmark.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const script=fs.readFileSync('scripts/photoshop/prepare_auto_editions.jsx','utf8');
function execute(strategy,options={}){
 const files=new Map(),saved=new Map(),stats={open:0,duplicate:0,merge:0,restore:0,text:0,close:0};let next=1;
 const unit=v=>({as:()=>Number(v)});let context;
 function File(path){this.fsName=path;this.length=(files.get(path)||'').length;this.exists=files.has(path);this.open=()=>true;this.read=()=>files.get(path);this.write=value=>{files.set(path,value);return true;};this.close=()=>{};}
 function bounds(v){return v.map(unit);}
 function layer(doc,name,kind,b,text){let value=text;const item={font:'SyntheticFont'};const record={id:doc.id*100+(name==='number'?1:2),name,kind,visible:true,allLocked:false,parent:doc,typename:'ArtLayer',bounds:bounds(b),textItem:item};Object.defineProperty(item,'contents',{get:()=>value,set:v=>{value=v;stats.text++;if(options.autoRename)record.name=v;}});return record;}
 function doc(name='staged',merged=null){
  const d={id:next++,mode:'RGB',bitsPerChannel:'EIGHT',width:unit(200),height:unit(120),resolution:300,colorProfileType:1,colorProfileName:'Synthetic ICC',_merged:merged,_region:null};
  d.layers=[layer(d,'number','TEXT',[130,95,170,105],'001 / 100'),layer(d,'plaque','PIXEL',[100,80,195,119],'')];
  if(options.preflightHidden){const artwork=layer(d,'artwork','PIXEL',[0,0,200,120],'');artwork.id=998;const obsolete=layer(d,'obsolete','TEXT',[50,90,80,100],'054 / 100');obsolete.id=999;d.layers.push(artwork,obsolete);}
  d.maskBounds=[20,30,60,70];
  d.resizeImage=(width,height,resolution,method)=>{
   const factor=width.as()/d.width.as();
   assert.equal(method,'bicubic-smoother');
   if(factor!==Math.floor(factor))assert.equal(height,null,'Fractional resize must constrain proportions');
   else assert(height,'Successful integer resize retains the existing two-dimension call');
   d.layers.forEach(l=>l.bounds=bounds(l.bounds.map(v=>v.as()*factor)));
   d.maskBounds=d.maskBounds.map(v=>v*factor);stats.resizedMask=d.maskBounds;
   d.height=unit(height?height.as():Math.floor(d.height.as()*factor+.5));d.width=width;
  };
  const rendering=()=>d._merged!==null?d._merged:(d.layers[0].visible?d.layers[0].textItem.contents:'');
  d.duplicate=(label,mergedOnly)=>{if(label==='edition-patch')stats.duplicate++;const copy=doc(label,rendering());context.app.documents.push(copy);context.app.activeDocument=copy;return copy;};
  d.crop=box=>{d._region=box.map(v=>v.as('px'));d.width=unit(d._region[2]-d._region[0]);d.height=unit(d._region[3]-d._region[1]);};
  d.mergeVisibleLayers=()=>{stats.merge++;d._merged=rendering();d.layers=[];};
  Object.defineProperty(d,'activeHistoryState',{get:()=>({text:d.layers[0].textItem.contents}),set:value=>{
   stats.restore++;if(options.restoreFailure)throw Error('synthetic_restore_failure');d._merged=null;d._region=null;d.width=unit(200);d.height=unit(120);d.layers=[layer(d,'number','TEXT',[130,95,170,105],value.text),layer(d,'plaque','PIXEL',[100,80,195,119],'')];if(options.autoRename)d.layers[0].name=value.text;if(options.restoreIdentityChanged)d.layers[0].id+=10;
  }});
  d.saveAs=(file,saveOptions,copy,extension)=>{
   if(file.fsName.endsWith('/profile-witness.psd')){files.set(file.fsName,witness);return;}
   if(options.exportFailure&&file.fsName.endsWith('/number-37.png'))throw Error('synthetic_export_failure');
   saved.set(file.fsName.split('/').pop(),JSON.stringify({width:d.width.as(),height:d.height.as(),region:d._region,text:rendering(),profile:d.colorProfileName,compression:saveOptions.compression,interlaced:saveOptions.interlaced}));
  };
  d.close=()=>{stats.close++;if(options.closeFailure&&name==='edition-patch')throw Error('synthetic_close_failure');context.app.documents.splice(context.app.documents.indexOf(d),1);};
  return d;
 }
 const uint=n=>{let b=Buffer.alloc(4);b.writeUInt32BE(n);return b;},header=Buffer.alloc(26);header.write('8BPS');header.writeUInt16BE(1,4);
 const resource=Buffer.concat([Buffer.from('8BIM'),Buffer.from([4,15,0,0]),uint(4),Buffer.from('test')]);
 const witness=Buffer.concat([header,uint(0),uint(resource.length),resource]).toString('latin1');files.set('C:/stage/expected.icc','test');
 context={File,Folder:function(path){this.fsName=path;},UnitValue:unit,ResampleMethod:{BICUBICSMOOTHER:'bicubic-smoother'},PNGSaveOptions:function(){},PhotoshopSaveOptions:function(){},Extension:{LOWERCASE:1},SaveOptions:{DONOTSAVECHANGES:1},DialogModes:{NO:0},ColorProfile:{NONE:0},DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:'EIGHT'},LayerKind:{TEXT:'TEXT'},SCPSDInspector:{inspect:()=>({document:{profile_state:'tagged'},layers:[]}),encode:JSON.stringify}};
 const old=doc('pre-existing');context.app={documents:[old],activeDocument:old,displayDialogs:'original-dialogs',fonts:{getByName:()=>({})},open:()=>{stats.open++;const opened=doc();context.app.documents.push(opened);context.app.activeDocument=opened;return opened;}};
 vm.createContext(context);vm.runInContext(script,context);let error=null,result;
 try{result=context.SCAutoEditionsPreparation.run({stage_root:'C:/stage',input:'C:/stage/input.psd',output_root:'C:/output',report:'C:/output/preparation.json',icc_path:'C:/stage/expected.icc',number_layer_name:'number',plaque_layer_name:'plaque',edition_total:100,reference_number:50,export_strategy:strategy,native_benchmark:options.admitted!==false,...(options.preflightHidden?{preflight_only:true,scale:1.5,...(options.reviewedHidden?{approved_hidden_number:{name:'obsolete',layer_id:999,bounds_px:[50,90,80,100]}}:{})}:{}),...(options.fractional?{scale:1.5,target_dimensions:[300,180],preparation_plan:{version:'selected-sku-fractional-v1'}}:{}),...(options.integer?{scale:4,target_dimensions:[800,480],preparation_plan:{version:'selected-sku-fractional-v1'}}:{})});}catch(e){error=e;}
 assert.equal(context.app.activeDocument,old);assert.equal(context.app.displayDialogs,'original-dialogs');
 return {stats,files,saved,error,result,remaining:context.app.documents.length};
}
const baseline=execute('duplicate_merged'),candidate=execute('history_merged_crop');
assert.equal(baseline.error,null);assert.equal(candidate.error,null);assert.equal(candidate.result,'AUTO_EDITIONS_PREPARED:100');
assert.equal(baseline.stats.open,1);assert.equal(candidate.stats.open,1);assert.equal(baseline.stats.duplicate,100);assert.equal(candidate.stats.duplicate,0);
assert.equal(candidate.stats.merge,100);assert.equal(candidate.stats.restore,100);assert.equal(candidate.stats.text,200);assert.equal(baseline.stats.text,200);
assert.deepEqual([...candidate.saved],[...baseline.saved]);assert.equal(candidate.saved.size,105);assert.equal(candidate.remaining,1);
const status=JSON.parse(candidate.files.get('C:/output/native-status.json'));assert(status.completed&&status.owned_document_closed);assert.equal(status.timings.number_samples.length,100);
for(const strategy of ['duplicate_merged','history_merged_crop']){
 const failure=execute(strategy,{exportFailure:true});assert(failure.error);assert.equal(failure.remaining,1);assert(!failure.files.has('C:/output/preparation.json'));
 const state=JSON.parse(failure.files.get('C:/output/native-status.json'));assert(!state.completed&&state.owned_document_closed);
}
assert(execute('history_merged_crop',{restoreFailure:true}).error);
const renamed=execute('history_merged_crop',{autoRename:true});assert.equal(renamed.error,null);assert.equal(renamed.saved.size,105);
assert(execute('history_merged_crop',{restoreIdentityChanged:true}).error);
const close=execute('duplicate_merged',{closeFailure:true});assert(close.error);assert.equal(JSON.parse(close.files.get('C:/output/native-status.json')).owned_document_closed,false);
const normal=execute('history_merged_crop',{admitted:false});assert.equal(normal.error,null);assert.equal(normal.saved.size,105);
assert(execute('unsafe').error);
const fractional=execute('duplicate_merged',{fractional:true});assert.equal(fractional.error,null);
const enlarged=JSON.parse(fractional.files.get('C:/output/preparation.json'));
assert.deepEqual(enlarged.dimensions,[300,180]);assert.equal(enlarged.preparation_geometry.scale,1.5);
assert.deepEqual(enlarged.original_number_bounds,[195,142.5,255,157.5]);
assert.deepEqual(enlarged.plaque_bounds,[150,120,292.5,178.5]);
assert.deepEqual(fractional.stats.resizedMask,[30,45,90,105]);
assert.deepEqual(enlarged.number_region,[191,138,259,162]);
assert.equal(enlarged.original_number_bounds[0]/300,130/200);
assert.equal(enlarged.original_number_bounds[1]/180,95/120);
assert.equal(enlarged.font,'SyntheticFont');assert.equal(fractional.saved.size,105);
assert.equal(JSON.parse(fractional.saved.get('master.png')).profile,'Synthetic ICC');
assert.equal(fractional.remaining,1);
const integer=execute('duplicate_merged',{integer:true});assert.equal(integer.error,null);
assert.deepEqual(JSON.parse(integer.files.get('C:/output/preparation.json')).dimensions,[800,480]);
console.log('V19 DOM model: one source open, 100 exports, default fidelity, candidate operation counts, owned cleanup, failure and admission checks passed. No native speed claim.');
console.log('Fractional model: constrained bicubic smoother, number/plaque/mask proportions, remeasured patch bounds, font/profile and owned cleanup passed. Native appearance/memory remain unverified.');

for(const reviewed of [false,true]){const r=execute('duplicate_merged',{preflightHidden:true,reviewedHidden:reviewed});assert.equal(r.error,null);assert.equal(r.result,'AUTO_EDITIONS_PREFLIGHT');const p=JSON.parse(r.files.get('C:/output/preparation.json'));assert.equal(p.resize_background.layer_id,reviewed?998:999);assert.equal(r.remaining,1);}
console.log('Preflight model: only exact reviewed obsolete text is excluded; unreviewed layers retain existing admission.');
