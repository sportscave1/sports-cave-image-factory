const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/ui/editor.js','utf8'),base='a'.repeat(151000),field={value:base};let scheduled=0,callback,writes=0;
const ctx={opened:{path:'header.html',source:base},$:()=>field,lastSource:base,stack:[{source:base}],undoBytes:0,dirty:false,recoveryTimer:0,setTimeout:fn=>{scheduled++;callback=fn;return scheduled;},clearTimeout(){},persist(){writes++;},msg(){},highlight(){}};
vm.createContext(ctx);
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b));
vm.runInContext(part('function scheduleRecovery','function scheduleHighlight')+part('function apply(value)','function modified()')+part('function modified()','function component()'),ctx);
const undo=source.match(/\$\("ed-undo"\)\.onclick=\(\)=>act\(async\(\)=>\{([\s\S]*?)\n    \}\);/)[1];vm.runInContext('async function undo(){'+undo+'}',ctx);
(async()=>{for(let i=0;i<210;i++){field.value+='x';ctx.modified();}assert.equal(scheduled,1);assert.equal(ctx.stack.length,100);assert(ctx.stack.slice(1).every(row=>row.undo&&!row.source));callback();assert.equal(writes,1);for(let i=0;i<10;i++)await ctx.undo();assert.equal(field.value,base+'x'.repeat(200));for(let i=0;i<89;i++)await ctx.undo();assert.equal(field.value,base);assert.equal(ctx.dirty,false);console.log('Inverse keystroke Undo, bounded original-state recovery and periodic storage scheduling passed');})().catch(e=>{console.error(e);process.exitCode=1});
