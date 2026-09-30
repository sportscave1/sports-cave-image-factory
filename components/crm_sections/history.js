/* Bounded recovery history, separate from the textarea's native undo stack. */
class SectionHistory {
 constructor(value, saved){this.states=Array.isArray(saved?.states)?saved.states.filter(v=>typeof v==='string').slice(-30):[value];this.index=Math.min(Math.max(0,saved?.index||0),this.states.length-1);this.record(value);}
 record(value){if(this.states[this.index]===value)return;this.states=this.states.slice(0,this.index+1);this.states.push(value);while(this.states.length>30||this.states.length>1&&this.states.reduce((n,v)=>n+v.length,0)>250000)this.states.shift();this.index=this.states.length-1;}
 undo(current){this.record(current);if(this.index>0)return this.states[--this.index];return current;}
 redo(){if(this.index<this.states.length-1)this.index++;return this.states[this.index];}
}
function insertAt(ids,id,target,after){const result=ids.filter(i=>i!==id);const index=result.indexOf(target);if(index<0||id===target)return [...ids];result.splice(index+(after?1:0),0,id);return result;}
if(typeof module!=='undefined')module.exports={SectionHistory,insertAt};
