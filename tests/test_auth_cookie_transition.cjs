const {chromium}=require('playwright');
const {execFileSync}=require('child_process');
const assert=require('assert');
const generate=`import ast,json,sc_auth
from pathlib import Path
from types import SimpleNamespace
node=next(n for n in ast.parse(Path('app.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='_auth_cookie_script')
outputs=[]
ns={'sc_auth':sc_auth,'json':json,'get_components_module':lambda:SimpleNamespace(html=lambda body,**kwargs:outputs.append(body))}
exec(compile(ast.Module(body=[node],type_ignores=[]),'cookie_fixture','exec'),ns)
ns['_auth_cookie_script']('synthetic-new-cookie',max_age_seconds=30*86400)
ns['_auth_cookie_script'](clear=True)
print(json.dumps(outputs))`;
const scripts=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-X','utf8','-c',generate],{encoding:'utf8'}));
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});
try{const context=await browser.newContext();await context.addCookies([{name:'sports_cave_auth',value:'synthetic-old-cookie',domain:'fixture.test',path:'/',secure:true,httpOnly:true,sameSite:'Lax'}]);
const page=await context.newPage();let mode=0,cleanups=0,loads=0;
await page.route('https://fixture.test/**',r=>{
 if(r.request().url().endsWith('/api/os/auth/clear-cookie')){cleanups++;return r.fulfill({status:204,headers:{'Set-Cookie':'sports_cave_auth=""; Max-Age=0; Path=/; HttpOnly; SameSite=Lax'}});}
 const script=loads++%2===0?scripts[mode]:'';
 return r.fulfill({contentType:'text/html',body:'<html><body>'+script+'</body></html>'});
});
await page.goto('https://fixture.test/');await page.waitForTimeout(300);
let cookies=await context.cookies();let cookie=cookies.find(c=>c.name==='sports_cave_auth');
assert.equal(cookie.value,'synthetic-new-cookie');assert.equal(cookie.httpOnly,false);assert(cookie.expires>Date.now()/1000+29*86400);
mode=1;await page.goto('https://fixture.test/');await page.waitForTimeout(300);
assert.equal((await context.cookies()).some(c=>c.name==='sports_cave_auth'),false);assert.equal(cleanups,2);
console.log('PASS old HttpOnly cookie replaced; 30-day normal cookie; logout clears cookie; no navigation polling');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
