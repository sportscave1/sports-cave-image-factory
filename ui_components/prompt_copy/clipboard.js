/* Shared write-only clipboard primitive. Never read clipboard contents. */
(function(root){
 async function copyText(text){
  try{if(root.navigator?.clipboard?.writeText&&root.isSecureContext){await root.navigator.clipboard.writeText(String(text));return true;}}catch{}
  let area;
  const active=root.document.activeElement;
  try{
   area=root.document.createElement('textarea');area.value=String(text);area.readOnly=true;
   area.style.cssText='position:fixed;left:0;top:0;opacity:0;pointer-events:none';
   root.document.body.appendChild(area);area.focus();area.select();area.setSelectionRange(0,area.value.length);
   return Boolean(root.document.execCommand('copy'));
  }catch{return false;}
  finally{area?.remove();try{active?.focus({preventScroll:true});}catch{}}
 }
 root.scCopyText=copyText;
 if(typeof module!=='undefined')module.exports={copyText};
})(typeof window!=='undefined'?window:globalThis);
