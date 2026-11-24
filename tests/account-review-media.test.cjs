const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../shopify_customer_account/node_modules/typescript');
function fixture(values={},request=()=>assert.fail('No submit while rendering')) {
 const source=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/AccountReview.jsx'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,jsxFactory:'h'}}).outputText;
 const module={exports:{}};let stateIndex=0;
 const h=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity).filter(Boolean)});
 const hooks={useState:value=>[Object.hasOwn(values,stateIndex)?values[stateIndex++]:((stateIndex++),value),()=>{}],useEffect:()=>{},useRef:value=>({current:value})};
 const jsx=(type,props)=>h(type,props,props?.children);
 vm.runInNewContext(code,{module,exports:module.exports,h,FormData,require:name=>name==='preact/jsx-runtime'?{jsx,jsxs:jsx}:name==='preact/hooks'?hooks:name==='./collection-image-utils.js'?{collectionThumbnail:value=>value}:name==='./account-review-utils.js'?{reviewProductId:()=> 'fixture'}:{}});
 const tree=module.exports.AccountReview({prompt:{reference:'private-reference',product_title:'Fixture edition'},certificate:{purchased_image_url:'https://cdn.shopify.com/lifestyle.jpg'},request,api:{}});
 const all=[];function walk(n){if(!n||typeof n!=='object')return;all.push(n);(n.children||[]).forEach(walk)}walk(tree);return all;
}
test('compact account form has one upload control below full-width setup guidance and image',()=>{
 const all=fixture();const modal=all.find(n=>n.type==='s-modal'),drop=all.filter(n=>n.type==='s-drop-zone');
 assert.equal(modal.props.heading,'Leave a review');assert.equal(modal.props.padding,'none');
 assert.equal(drop.length,1);assert.equal(drop[0].props.label,'Add photo/video (optional)');assert.equal(drop[0].props.multiple,true);assert.match(drop[0].props.accept,/video\/mp4/);
 assert.equal(all.filter(n=>n.type==='s-text'&&n.children.includes('Add photo/video (optional)')).length,0);
 const guidance=all.find(n=>n.children.includes('Show us your setup'));const image=all.find(n=>n.type==='s-image'&&n.props.alt==='Your edition in a room');
 assert.equal(image.props.inlineSize,'fill');assert.ok(all.indexOf(guidance)<all.indexOf(image)&&all.indexOf(image)<all.indexOf(drop[0]));
 assert.ok(all.indexOf(all.find(n=>n.type==='s-text-area'))<all.indexOf(guidance));
 assert.equal(all.find(n=>n.type==='s-text-area').props.rows,1);assert.equal(all.find(n=>typeof n.type==='function'&&n.props.onChange&&!n.props.compact).props.rating,5);
 assert.equal(all.filter(n=>n.props.href||n.props.target==='_blank').length,0);
});
test('compact form still sends text, photo and video through the native multipart endpoint',async()=>{
 const photo=new File(['photo'],'photo.jpg',{type:'image/jpeg'}),video=new File(['video'],'video.mp4',{type:'video/mp4'});let submitted;
 const all=fixture({2:'Synthetic collector',4:'My title',5:'A proper native review',6:[photo,video]},async(path,options)=>{submitted={path,body:options.body}});
 await all.find(n=>n.props.slot==='primary-action').props.onClick();
 assert.equal(submitted.path,'/api/collector-vault/review');assert.equal(submitted.body.get('review_reference'),'private-reference');assert.equal(submitted.body.get('rating'),'5');assert.equal(submitted.body.get('reviewer_name'),'Synthetic collector');assert.equal(submitted.body.get('display_consent'),'yes');assert.deepEqual(submitted.body.getAll('media').map(f=>f.name),['photo.jpg','video.mp4']);
 assert.equal(all.filter(n=>n.props.accessibilityLabel?.startsWith('Remove ')).length,2);
 assert.equal(all.filter(n=>n.type==='s-drop-zone').length,0);
 assert.ok(all.some(n=>n.type==='s-button'&&n.children.includes('Change photo/video')));
});
