'use strict';
const formPage=location.pathname==='/demo/form',signin=location.pathname==='/demo/signin';
document.getElementById('home').hidden=formPage||signin;
document.getElementById('formPage').hidden=!formPage;
document.getElementById('signin').hidden=!signin;
document.getElementById('fakeLogin').onclick=()=>location.assign('/demo');
document.getElementById('image').onchange=()=>{document.getElementById('uploadStatus').textContent='Upload ready';};
document.getElementById('reveal').onclick=()=>setTimeout(()=>{
  if(document.getElementById('continue'))return;
  const b=document.createElement('button');b.type='button';b.id='continue';b.textContent='Continue after delay';
  b.onclick=()=>{b.textContent='Delayed content accepted';};document.getElementById('delayed').append(b);
},650);
document.getElementById('productForm').onsubmit=ev=>{
  ev.preventDefault();
  const result={product:document.getElementById('product').value,headline:document.getElementById('headline').value,
  url:document.getElementById('destination').value,category:document.getElementById('category').value,
  approved:document.getElementById('approved').checked,file:document.getElementById('image').files[0]?.name||'',
  submissions:Number(document.getElementById('result').dataset.submissions||0)+1};
  const e=document.getElementById('result');e.dataset.submissions=String(result.submissions);e.textContent=JSON.stringify(result);
};
