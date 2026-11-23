const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../shopify_customer_account/node_modules/typescript');
const source=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/MySportsCaveCollection.jsx'),'utf8');
const commerceModule={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/account-commerce.js'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports:commerceModule.exports,module:commerceModule});
const compiled=ts.transpileModule(source+'\nexport {CertificateViewer,CertificateGallery,CollectionUpsells,FramedCertificatePreview,FramedCertificateOffer};',{
 compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,jsxFactory:'h'},fileName:'collection.jsx',
}).outputText;
function fixture({existing=false,failure=false}={}){
 const product={variant_id:'gid://shopify/ProductVariant/42',variants:[{variant_id:'gid://shopify/ProductVariant/42',color:'Oak',contextual_price:{amount:'79',currencyCode:'USD'}}]};
 const state=[{status:'ready',product,certificateReference:'owned-fixture'},'Oak',{status:'idle',message:'',checkoutUrl:''}];
 let index=0,queries=0;const calls=[];
 const hooks={useState:initial=>{const i=index++;return [state[i]??initial,v=>state[i]=v]},useEffect:()=>{},useRef:v=>({current:v})};
 const module={exports:{}};
 const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity).filter(Boolean)});
 const utils={formatFramePrice:p=>p?`${p.currencyCode} ${p.amount}`:'',frameCartInput:(id,reference)=>({lines:[{merchandiseId:id,quantity:1,attributes:[{key:'_sports_cave_frame_request',value:reference}]}]})};
 const fetch=async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:!failure,status:failure?503:200,json:async()=>url.endsWith('/request')?{request_reference:'owned-request',cart_handoff_url:'https://fixture.test/launch',...(existing?{checkout_url:'https://fixture.test/checkout'}:{})}:{ok:true}}};
 const jsx=(type,props)=>h(type,props,...[props?.children]);
 vm.runInNewContext(compiled,{exports:module.exports,module,h,AbortController,fetch,require:name=>name==='preact/jsx-runtime'?{jsx,jsxs:jsx}:name==='preact/hooks'?hooks:name==='./vault-utils.js'?utils:name==='./account-commerce.js'?commerceModule.exports:{}});
 const api={sessionToken:{get:async()=>'fixture-only'},query:async()=>{queries++;return {data:{cartCreate:{cart:{id:'fixture-cart',checkoutUrl:'https://fixture.test/checkout'}}}}},i18n:{formatNumber:String}};
 return {exports:module.exports,state,calls,get queries(){return queries},view:()=>{index=0;return module.exports.CertificateViewer({certificate:{key:'fixture',framingOnly:true,product_title:'Fixture edition'},api,apiBaseUrl:'https://fixture.test',country:'US',onClose:()=>{}})}};
}
function find(node,predicate){if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of node.children||[]){const match=find(child,predicate);if(match)return match;}return null;}
test('frame picker uses maximum native modal with a larger preview column',()=>{
 const tree=fixture().view();assert.equal(tree.props.size,'max');
 assert.ok(find(tree,n=>n.type==='s-grid' && /1\.25fr/.test(n.props.gridTemplateColumns)));
 assert.equal(tree.props.heading,'Frame your certificate');
});
for(const existing of [false,true])test(`Add stays over account and opens cart confirmation, existing cart: ${existing}`,async()=>{
 const f=fixture({existing});const offer=find(f.view(),n=>n.type?.name==='FramedCertificateOffer');
 await offer.props.onAdd();assert.equal(f.state[2].status,'ready');assert.equal(f.queries,existing?0:1);
 assert.equal(f.calls[0].body.frame_variant_id,'gid://shopify/ProductVariant/42');assert.equal(f.calls[0].body.country,'US');
 const cart=f.view();assert.equal(cart.props.heading,'Your framed certificate cart');
 assert.equal(find(cart,n=>n.type==='s-button'&&n.children.includes('Continue to checkout')).props.href,'https://fixture.test/launch');
 assert.ok(find(cart,n=>n.type==='s-button'&&n.props.command==='--hide'));
 assert.ok(find(cart,n=>n.children.includes('USD 79')));
 assert.equal(find(cart,n=>n.type?.name==='FramedCertificateOffer'),null);
});
test('failed Add keeps the frame picker and never presents checkout',async()=>{
 const f=fixture({failure:true});await find(f.view(),n=>n.type?.name==='FramedCertificateOffer').props.onAdd();
 assert.equal(f.state[2].status,'error');assert.equal(f.queries,0);assert.equal(f.view().props.size,'max');
 assert.equal(find(f.view(),n=>n.type==='s-button'&&n.props.href),null);
});
test('certificate gallery uses two desktop columns and one mobile column without horizontal scrolling',()=>{
 const tree=fixture().exports.CertificateGallery({certificates:[{key:'1'},{key:'2'}],onOpen:()=>{}});
 assert.equal(tree.type,'s-grid');assert.equal(tree.props.gridTemplateColumns,'@container (inline-size > 750px) 1fr 1fr, 1fr');
});

test('all three certificate previews remain mounted and eagerly load for colour switching',()=>{
 const f=fixture();
 const tree=f.exports.FramedCertificatePreview({certificate:{product_title:'Fixture'},previewUrl:'https://fixture.test/asset?token=owner',color:'Oak'});
 const boxes=tree.children;assert.equal(boxes.length,3);
 assert.deepEqual(Array.from(boxes,b=>b.props.display),['none','auto','none']);
 assert.deepEqual(Array.from(boxes,b=>b.props.accessibilityVisibility),['hidden','visible','hidden']);
 for(const box of boxes){assert.equal(box.children[0].props.loading,'eager');assert.equal(box.children[0].props.objectFit,'contain');}
 assert.match(boxes[1].children[0].props.src,/frame=oak$/);
});
