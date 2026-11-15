'use strict';
const $=id=>document.getElementById(id),fragment=new URLSearchParams(location.hash.slice(1));
if(fragment.get('origin'))$('site').value=fragment.get('origin');
if(fragment.get('code'))$('code').value=fragment.get('code');
history.replaceState(null,'',location.pathname);
async function call(path){
 const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Recorder-Local':'1'},body:JSON.stringify({origin:$('site').value,code:$('code').value,name:$('name').value})});
 const data=await response.json();if(!response.ok)throw Error(data.error||'Could not connect. Try a new code.');return data;
}
$('pairForm').onsubmit=async e=>{e.preventDefault();try{const data=await call('/pair/inspect');$('account').textContent='Connect '+$('name').value+' to '+data.account+' at '+$('site').value+'?';$('approval').hidden=false;$('message').textContent='Approve only if you requested this connection in Sports Cave OS.';}catch(e){$('message').textContent=e.message;}};
$('approve').onclick=async()=>{try{$('approve').disabled=true;await call('/pair/approve');$('code').value='';$('pairForm').hidden=true;$('approval').hidden=true;$('message').textContent='PC connected. Return to Sports Cave OS and press Record.';}catch(e){$('message').textContent=e.message;$('approve').disabled=false;}};
