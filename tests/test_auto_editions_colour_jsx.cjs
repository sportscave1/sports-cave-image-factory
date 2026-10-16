// The ExtendScript DOM uses ColorProfile, unlike the UXP ColorProfileType enum.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={app:{version:'synthetic'},ColorProfile:{NONE:0,WORKING:1,CUSTOM:2}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('scripts/photoshop/inspect_psd_editions.jsx','utf8'),context);
const document=()=>({width:{as:()=>20},height:{as:()=>10},resolution:300,mode:'RGB',bitsPerChannel:'EIGHT',layers:[]});
for(const type of [context.ColorProfile.WORKING,context.ColorProfile.CUSTOM]){
 const doc={...document(),colorProfileType:type,colorProfileName:'Custom RGB'};
 const row=context.SCPSDInspector.inspect(doc,{}).document;
 assert.equal(row.profile_state,'tagged');assert.equal(row.profile,'Custom RGB');
}
let doc={...document(),colorProfileType:context.ColorProfile.NONE};
Object.defineProperty(doc,'colorProfileName',{get(){throw Error('no assigned profile');}});
assert.equal(context.SCPSDInspector.inspect(doc,{}).document.profile_state,'untagged');
doc=document();Object.defineProperty(doc,'colorProfileType',{get(){throw Error('inspection unavailable');}});
assert.equal(context.SCPSDInspector.inspect(doc,{}).document.profile_state,'inspector_failure');
vm.runInContext(fs.readFileSync('scripts/photoshop/prepare_auto_editions.jsx','utf8'),context);
const uint=n=>{const b=Buffer.alloc(4);b.writeUInt32BE(n);return b;};
const block=Buffer.concat([Buffer.from('8BIM'),Buffer.from([4,15,0,0]),uint(4),Buffer.from('test')]);
const header=Buffer.alloc(26);header.write('8BPS');header.writeUInt16BE(1,4);
const witness=Buffer.concat([header,uint(0),uint(block.length),block]).toString('latin1');
assert.equal(context.SCAutoEditionsPreparation.witnessICC(witness),'test');
assert.throws(()=>context.SCAutoEditionsPreparation.witnessICC(witness.slice(0,-1)),/profile_inspector_failure/);
console.log('Photoshop ICC inspection: tagged custom/working, genuinely untagged and inspector failure passed.');
