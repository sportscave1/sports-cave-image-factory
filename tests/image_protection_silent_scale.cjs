// Reuse actual scale/drag/size viewer regression with silent protection active.
const fs=require('node:fs');
const path=require.resolve('./wall_preview_completion_fixture.cjs');const fixture=require(path);
require.cache[path].exports=()=>fixture()+`<script>
const originalFetch=window.fetch;window.fetch=(url,options)=>String(url)==='https://fixture.test/protection-config'?Promise.resolve(new Response(JSON.stringify({enabled:true,showCopyrightMessage:true}),{headers:{'Content-Type':'application/json'}})):originalFetch(url,options);
</script><script data-sc-protection-config="https://fixture.test/protection-config">${fs.readFileSync('shopify_theme/assets/sports-cave-image-protection.js','utf8')}</script>`;
require('./wall_preview_initial_scale.cjs');
