const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../shopify_customer_account/node_modules/typescript');
const source=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/MySportsCaveCollection.jsx'),'utf8');
const commerceModule={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/account-commerce.js'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:commerceModule.exports,module:commerceModule});
const compiled=ts.transpileModule(source+'\nexport {CertificateViewer,CertificateGallery,CollectionUpsells,CollectionShowcase,FramedCertificatePreview,FramedCertificateOffer};',{
 compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,jsxFactory:'h'},fileName:'collection.jsx',
}).outputText;
function fixture({existing=false,failure=false}={}){
 const product={variant_id:'gid://shopify/ProductVariant/42',variants:[{variant_id:'gid://shopify/ProductVariant/42',color:'Oak',contextual_price:{amount:'79',currencyCode:'USD'}}]};
 const state=[{status:'ready',product,certificateReference:'owned-fixture'},'Oak',{status:'idle',message:'',checkoutUrl:''}];
 let index=0,queries=0;const calls=[],navigations=[];
 const hooks={useState:initial=>{const i=index++;return [state[i]??initial,v=>state[i]=v]},useEffect:()=>{},useRef:v=>({current:v})};
 const module={exports:{}};
 const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity).filter(Boolean)});
 const utils={formatFramePrice:p=>p?`${p.currencyCode} ${p.amount}`:'',frameCartInput:(id,reference)=>({lines:[{merchandiseId:id,quantity:1,attributes:[{key:'_sports_cave_frame_request',value:reference}]}]})};
 const fetch=async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:!failure,status:failure?503:200,json:async()=>url.endsWith('/request')?{request_reference:'owned-request',cart_handoff_url:'https://fixture.test/launch',...(existing?{checkout_url:'https://fixture.test/checkout'}:{})}:{ok:true}}};
 const jsx=(type,props)=>h(type,props,...[props?.children]);
 vm.runInNewContext(compiled,{exports:module.exports,module,h,AbortController,fetch,navigation:{navigate:url=>navigations.push(url)},require:name=>name==='preact/jsx-runtime'?{jsx,jsxs:jsx}:name==='preact/hooks'?hooks:name==='./vault-utils.js'?utils:name==='./account-commerce.js'?commerceModule.exports:name==='./collection-performance.js'?{timedOperation:(_a,_b,_o,work)=>work(),operationForPath:()=>null}:name==='./collection-image-utils.js'?{collectionThumbnail:value=>value}:{}});
 const api={sessionToken:{get:async()=>'fixture-only'},query:async()=>{queries++;return {data:{cartCreate:{cart:{id:'fixture-cart',checkoutUrl:'https://fixture.test/checkout'}}}}},i18n:{formatNumber:String}};
 return {exports:module.exports,state,calls,navigations,get queries(){return queries},view:()=>{index=0;return module.exports.CertificateViewer({certificate:{key:'fixture',framingOnly:true,product_title:'Fixture edition'},api,apiBaseUrl:'https://fixture.test',country:'US',onClose:()=>{}})}};
}
function find(node,predicate){if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of node.children||[]){const match=find(child,predicate);if(match)return match;}return null;}
test('frame picker fits content with balanced columns and a full-width primary Add',()=>{
 const tree=fixture().view();assert.equal(tree.props.size,'large-100');
 assert.ok(find(tree,n=>n.type==='s-grid' && /1\.1fr/.test(n.props.gridTemplateColumns)));
 assert.equal(tree.props.heading,'Frame your certificate');
 const offer=fixture().exports.FramedCertificateOffer({product:{variants:[{color:'Black',contextual_price:{amount:'99',currencyCode:'AUD'}}]},frameColor:'Black',onColorChange:()=>{},checkoutState:{status:'idle'},onAdd:()=>{},formatNumber:String});
 assert.equal(find(offer,n=>n.type==='s-button'&&n.props.onClick).props.inlineSize,'fill');
});
for(const existing of [false,true])test(`Add opens the storefront cart directly, existing cart: ${existing}`,async()=>{
 const f=fixture({existing});const offer=find(f.view(),n=>n.type?.name==='FramedCertificateOffer');
 await offer.props.onAdd();assert.equal(f.state[2].status,'adding');assert.equal(f.queries,existing?0:1);
 assert.equal(f.calls[0].body.frame_variant_id,'gid://shopify/ProductVariant/42');assert.equal(f.calls[0].body.country,'US');
 assert.deepEqual(f.navigations,['https://fixture.test/launch']);
 assert.equal(f.calls.length,existing?1:2);
 if(!existing)assert.ok(f.calls[1].url.endsWith('/cart-created'));
 const cart=f.view();assert.equal(cart.props.heading,'Frame your certificate');
 assert.equal(find(cart,n=>n.type==='s-button'&&n.children.includes('Continue to cart')),null);
 await find(cart,n=>n.type?.name==='FramedCertificateOffer').props.onAdd();
 assert.equal(f.navigations.length,1);assert.equal(f.calls.length,existing?1:2);
});

test('failed Add keeps the frame picker and never presents checkout',async()=>{
 const f=fixture({failure:true});await find(f.view(),n=>n.type?.name==='FramedCertificateOffer').props.onAdd();
 assert.equal(f.navigations.length,0);assert.equal(f.state[2].status,'error');assert.equal(f.queries,0);assert.equal(f.view().props.size,'large-100');
 assert.equal(find(f.view(),n=>n.type==='s-button'&&n.props.href),null);
});
test('certificate gallery uses two desktop columns and one mobile column without horizontal scrolling',()=>{
 const tree=fixture().exports.CertificateGallery({certificates:[{key:'1'},{key:'2'}],onOpen:()=>{}});
 assert.equal(tree.type,'s-grid');assert.equal(tree.props.gridTemplateColumns,'@container (inline-size > 750px) 1fr 1fr, 1fr');
});

test('all three certificate previews remain mounted and eagerly load for colour switching',()=>{
 const f=fixture();
 const tree=f.exports.FramedCertificatePreview({certificate:{product_title:'Fixture'},previewUrl:'https://fixture.test/asset?token=owner',color:'Oak'});
 const boxes=tree.children[0].children;assert.equal(boxes.length,3);
 assert.deepEqual(Array.from(boxes,b=>b.props.display),['none','auto','none']);
 assert.deepEqual(Array.from(boxes,b=>b.props.accessibilityVisibility),['hidden','visible','hidden']);
 for(const box of boxes){assert.equal(box.children[0].props.loading,'eager');assert.equal(box.children[0].props.objectFit,'contain');}
 assert.match(boxes[1].children[0].props.src,/frame=oak$/);
 assert.equal(boxes[1].children[0].props.srcSet,'https://fixture.test/asset?token=owner&frame=oak&w=400 400w, https://fixture.test/asset?token=owner&frame=oak&w=1000 1000w');
});

test('showcase uses raw certificate and preserves original downloads; selection follows the purchased variant',()=>{
 const f=fixture();const items=[{key:'black',product_title:'Edition â€“ Athlete',variant_title:'Black / M',edition_display:'#027 / 100',purchased_image_url:'https://fixture.test/black.jpg',certificate_preview_image_url:'https://fixture.test/raw.png',frame_preview_url:'https://fixture.test/framed.webp',certificate_pdf_url:'https://fixture.test/original.pdf',certificate_download_url:'https://fixture.test/asset?token=print'}, {key:'oak',product_title:'Edition â€“ Athlete',variant_title:'Oak / M',edition_display:'#028 / 100',purchased_image_url:'https://fixture.test/oak.jpg',certificate_preview_image_url:'https://fixture.test/raw2.png'}];
 let selected;const tree=f.exports.CollectionShowcase({certificates:items,activeCertificate:items[0],onSelect:key=>selected=key,onOpen:()=>{}});
 assert.equal(find(tree,n=>n.type==='s-image'&&n.props.src==='https://fixture.test/raw.png').props.objectFit,'contain');
 assert.equal(find(tree,n=>n.type==='s-link'&&n.children.includes('Download printable certificate')).props.href,'https://fixture.test/asset?token=print');
 const choice=find(tree,n=>n.type==='s-clickable'&&n.props.accessibilityLabel.includes('Oak / M'));choice.props.onClick();assert.equal(selected,'oak');
 const second=f.exports.CollectionShowcase({certificates:items,activeCertificate:items[1],onSelect:()=>{},onOpen:()=>{}});
 assert.ok(find(second,n=>n.type==='s-image'&&n.props.src==='https://fixture.test/oak.jpg'));
 assert.ok(find(second,n=>n.type==='s-image'&&n.props.src==='https://fixture.test/raw2.png'));
 assert.ok(find(tree,n=>n.type==='s-box'&&n.props.display==='none'&&n.props.accessibilityVisibility==='hidden'));
});
test('paired products keep the smart order and return only two published available editions',()=>{
 const product=(id,available=true)=>({id,handle:id,availableForSale:available});
 const result=commerceModule.exports.pairedProducts(['1','2','3','4','5'],[product('5'),product('3'),product('1',false),null,product('4')]);
 assert.deepEqual(Array.from(result,p=>p.id),['3','4']);
});

test('native responsive grid expressions escape reserved CSS punctuation',()=>{
 for(const file of ['MySportsCaveCollection.jsx','AccountReview.jsx']){
 const jsx=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src',file),'utf8');
 for(const match of jsx.matchAll(/gridTemplateColumns="(@container[^"]+)"/g)){
  const value=match[1];if(value.includes('minmax(')) assert.match(value,/\) '[^']+', '[^']+'$/);
 }
 }
});

test('mobile edition carousel wraps with dedicated non-overlay arrow columns and no dropdown',()=>{
 const f=fixture();const items=[{key:'one',product_title:'One',variant_title:'Black / M - 30 x 45 cm',edition_display:'#001 / 100'},{key:'two',product_title:'Two',variant_title:'Oak / XL - 62 x 87 cm',edition_display:'#002 / 100'}];let selected;
 const tree=f.exports.CollectionShowcase({certificates:items,activeCertificate:items[0],onSelect:key=>selected=key,onOpen:()=>{}});
 assert.equal(find(tree,n=>n.type==='s-select'),null);
 assert.ok(find(tree,n=>n.type==='s-grid'&&n.props.gridTemplateColumns==='44px minmax(0, 1fr) 44px'));
 find(tree,n=>n.props.accessibilityLabel==='Next edition').props.onClick();assert.equal(selected,'two');
 find(tree,n=>n.props.accessibilityLabel==='Previous edition').props.onClick();assert.equal(selected,'two');
});
test('display variants omit measurements while preserving frame and size labels',()=>{
 for(const [input,want] of [['Black / S- 21 Ã— 30 cm (8.3 Ã— 11.8 in)','Black / S'],['Oak / XL - 62 x 87 cm','Oak / XL'],['Unframed / M - 30 x 45 cm','Unframed / M'],['White / L','White / L']])assert.equal(commerceModule.exports.compactVariant(input),want);
});

test('compact review stars stay in a fixed five-column row',()=>{
 const reviewModule={exports:{}};
 const reviewSource=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/AccountReview.jsx'),'utf8')+'\nexport {StarRating};';
 const reviewCode=ts.transpileModule(reviewSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,jsxFactory:'h',target:ts.ScriptTarget.ES2022}}).outputText;
 const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity).filter(Boolean)});
 const jsx=(type,props)=>h(type,props,...[props?.children]);
 vm.runInNewContext(reviewCode,{exports:reviewModule.exports,module:reviewModule,h,require:name=>name==='preact/jsx-runtime'?{jsx,jsxs:jsx}:{}});
 const stars=reviewModule.exports.StarRating({rating:5,onChange:()=>{},compact:true});
 assert.equal(stars.type,'s-grid');assert.equal(stars.props.gridTemplateColumns,'repeat(5, minmax(0, 1fr))');assert.equal(stars.props.inlineSize,'120px');assert.equal(stars.children.length,5);
 assert.ok(stars.children.every(button=>button.props.padding==='none'));
});

test('mobile frame preview uses available viewport height and the description stays visible',()=>{
 const f=fixture();const tree=f.view();
 assert.ok(find(tree,n=>n.type==='s-text'&&n.children.includes('Your numbered certificate, professionally printed and framed.')));
 const preview=f.exports.FramedCertificatePreview({certificate:{},previewUrl:'https://fixture.test/asset?token=owner',color:'Black'});
 assert.match(preview.props.gridTemplateColumns,/100dvh - 440px/);
 assert.match(preview.props.gridTemplateColumns,/340px/);
});
